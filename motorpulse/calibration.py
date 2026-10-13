"""MP-038: validation-only synthetic anomaly threshold operating-point research.

No model or preprocessing refit. The portable MP-035 artifact is immutable;
selection uses exclusively validation labels and scores, then test is audited
once with the frozen selected numeric threshold. Not field calibration.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from math import isfinite
from pathlib import Path
import platform
import sys
from typing import Any

from .anomaly import _events, _score, _validated_sources, _vector
from .evaluation import RULE_ALERTS, _truth
from .experiment import MAX_CONFIG_BYTES, _write_markdown, validate_experiment_config
from .feature_pipeline import validate_window_contract
from .ims import _read_strict_json, write_local_manifest
from .model_artifact import load_model_artifact
from .robustness import _metrics, from_experiment as verify_experiment_partition
from .sim import classify
from .splits import _hash

CALIBRATION_VERSION = "1.0.0"
MAX_CURVE_POINTS = 35
MAX_TARGET_FPR = 1.0


def _target(value: Any) -> float:
    if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= MAX_TARGET_FPR:
        raise ValueError("target_fpr must be a finite number between 0 and 1, not bool")
    return float(value)


def choose_threshold(validation_rows: list[dict], *, target_fpr: float) -> dict:
    """Select the *lowest nonnegative* threshold with FP/N <= target FPR.

    Exactly score > threshold constitutes an alert, and equal scores cannot
    be split. Target is an empirical **validation** FPR, not a guaranteed
    operating rate. This function accepts no test-partition input.
    """
    fpr = _target(target_fpr)
    if type(validation_rows) is not list:
        raise ValueError("validation rows must be a list")
    negatives = []
    positives = 0
    for row in validation_rows:
        if type(row) is not dict or type(row.get("positive")) is not bool:
            raise ValueError("validation rows require boolean synthetic effective truth")
        score = row.get("score")
        if type(score) not in (float, int) or not isfinite(score) or score < 0:
            raise ValueError("validation rows require nonnegative finite frozen scores")
        if row["positive"]:
            positives += 1
        else:
            negatives.append(float(score))
    if not negatives:
        raise ValueError("validation threshold calibration requires eligible negative windows")
    negatives.sort(reverse=True)
    allowed_fp = int(fpr * len(negatives))
    # Lowest threshold yielding <= allowed_fp under a STRICT score > cutoff.
    # The (allowed_fp+1)-th largest negative score defines the cutoff.
    # Equal-score ties can make empirical FPR strictly smaller than target.
    cutoff = negatives[allowed_fp] if allowed_fp < len(negatives) else 0.0
    observed_fp = sum(value > cutoff for value in negatives)
    if observed_fp > allowed_fp:
        raise ValueError("invalid tie-aware validation threshold")
    return {
        "threshold": cutoff, "target_false_positive_rate": fpr,
        "allowed_validation_false_positives": allowed_fp,
        "achieved_validation_false_positives": observed_fp,
        "achieved_validation_false_positive_rate": observed_fp / len(negatives),
        "validation_eligible_negative_windows": len(negatives),
        "validation_eligible_positive_windows": positives,
        "selection_policy": (
            "lowest_nonnegative_cutoff_meeting_validation_FPR_budget; "
            "strict_score_greater_than_threshold; score ties indivisible"
        ),
        "caveat": "Empirical simulated validation FPR only; no guaranteed future/industrial alarm rate.",
    }


def _replay_partition(plan: dict, sources: dict, model: dict, partition: str,
                      baseline: dict) -> list[dict]:
    """Recompute only existing trained scores; reject contradictory rule labels."""
    rows = []
    counts = Counter()
    skipped = Counter()
    for group in sorted(plan["partitions"][partition]["group_ids"]):
        source = sources[group]
        for event in _events(source):
            validate_window_contract(event)
            positive, scenario = _truth(event)
            quality = event.get("sensor_quality")
            if quality not in ("good", "missing", "outlier"):
                raise ValueError("unexpected sensor quality")
            health = event.get("health")
            reasons = event.get("reasons")
            if quality == "good":
                measured = _vector(event)
                expected_health, expected_reasons = classify(
                    event["rms_g"], event["temperature_c"], event["crest_factor"]
                )
                if health != expected_health or reasons != expected_reasons:
                    raise ValueError("source rule decision/reasons changed")
                score = _score(measured, model["center"], model["effective_scales"])
                if not isfinite(score):
                    raise ValueError("nonfinite frozen anomaly score")
                rules = health in RULE_ALERTS
            else:
                expected = "unavailable" if quality == "missing" else "suspect"
                if health != expected or type(reasons) is not list or not reasons:
                    raise ValueError("sensor abstention contradicts source health")
                score = None
                rules = False
                skipped[quality] += 1
            rows.append({
                "group_id": group, "asset_id": event["asset_id"], "tick": event["tick"],
                "timestamp_utc": event["timestamp_utc"], "scenario": scenario,
                "positive": positive, "eligible": quality == "good",
                "quality": quality, "score": score, "rule_alert": rules,
                "step_seconds": source["step_seconds"],
            })
            counts[group] += 1
    if (len(rows) != baseline["comparison_cohort"]["total_windows"] or
            sum(r["eligible"] for r in rows) != baseline["comparison_cohort"]["eligible_both_methods"] or
            dict(sorted(skipped.items())) != baseline["comparison_cohort"]["abstentions"] or
            sorted(counts) != sorted(baseline["evaluated_groups"])):
        raise ValueError("replayed source cohort differs from MP-011 baseline")
    for group in counts:
        if counts[group] != sources[group]["records"]:
            raise ValueError("held-out group event count differs from source")
    return rows


def _at_threshold(rows: list[dict], threshold: float) -> list[dict]:
    if type(threshold) not in (int, float) or not isfinite(threshold) or threshold < 0:
        raise ValueError("invalid selected threshold")
    return [
        {**r, "anomaly_alert": r["score"] > threshold}
        for r in rows if r["eligible"]
    ]


def _compare(rows: list[dict], threshold: float) -> dict:
    eligible = _at_threshold(rows, threshold)
    return {
        "model": _metrics(eligible, "anomaly_alert"),
        "rules": _metrics(eligible, "rule_alert"),
    }


def _check_original(rows: list[dict], original: float, baseline: dict) -> None:
    if _compare(rows, original) != baseline["overall"]:
        raise ValueError("replayed original model/rules disagree with MP-011")
    for group, metrics in baseline["by_run"].items():
        if _compare([r for r in rows if r["group_id"] == group], original) != metrics:
            raise ValueError("replayed original per-run results differ from MP-011")


def _curve(rows: list[dict], selected: float, original: float) -> list[dict]:
    """At most 35 representative candidate scores, not an exhaustive ROC."""
    scores = sorted({r["score"] for r in rows if r["eligible"]})
    if not scores:
        raise ValueError("no validation scores for threshold tradeoff")
    # Index sampling does not change selection (which uses every negative).
    grid = {scores[i * (len(scores)-1) // 30] for i in range(31)}
    candidates = sorted(grid | {0.0, selected, original})
    if len(candidates) > MAX_CURVE_POINTS:
        raise ValueError("threshold curve point bound exceeded")
    return [
        {
            "threshold": cutoff,
            "is_selected_validation_cutoff": cutoff == selected,
            "is_original_training_cutoff": cutoff == original,
            "validation": _compare(rows, cutoff)["model"],
        }
        for cutoff in candidates
    ]


def calibrate_experiment(root: str | Path, *, target_fpr: float = .05) -> dict:
    """Separate validation selection phase from one subsequent test audit."""
    goal = _target(target_fpr)
    directory = Path(root)
    # Validate original MP-033 file index, MP-035 portable model, MP-030 split,
    # all run-specific dataset cards and MP-011 metrics, including both holdouts.
    verified_validation = verify_experiment_partition(directory, partition="validation")
    cfg = validate_experiment_config(_read_strict_json(
        directory / "experiment-config.json", MAX_CONFIG_BYTES))
    plan = _read_strict_json(directory / "split-plan.json", 256 * 1024)
    manifests = [directory / "runs" / f"seed-{seed:010d}" / "manifest.json"
                 for seed in cfg["seeds"]]
    model = load_model_artifact(directory / "model-artifact.json",
                                plan=plan, manifests=manifests)
    sources = _validated_sources(plan, manifests)
    baseline_validation = _read_strict_json(directory / "validation-metrics.json", 8*1024*1024)
    if baseline_validation.get("evaluation_sha256") != verified_validation["baseline_evaluation_sha256"]:
        raise ValueError("validation report checksum identity differs from verified experiment")
    original = model["calibration"]["threshold"]
    validation = _replay_partition(plan, sources, model, "validation", baseline_validation)
    _check_original(validation, original, baseline_validation)

    # SELECTION BOUNDARY: From here until selection is frozen, *only* validation
    # event scores and truth may influence the numeric cutoff and curve.
    eligible_validation = [r for r in validation if r["eligible"]]
    choice = choose_threshold(eligible_validation, target_fpr=goal)
    selected = choice["threshold"]
    validation_selected = _compare(validation, selected)
    if validation_selected["model"]["fp"] != choice["achieved_validation_false_positives"]:
        raise ValueError("selection and validation confusion matrix disagree")
    curve = _curve(validation, selected, original)

    # TEST BOUNDARY: Read test truth only **after** the threshold is chosen.
    # Test cannot alter selection. Original portable model is NOT modified.
    verified_test = verify_experiment_partition(directory, partition="test")
    if (verified_test["model_sha256"] != verified_validation["model_sha256"] or
            verified_test["experiment_sha256"] != verified_validation["experiment_sha256"] or
            verified_test["model_artifact_sha256"] != verified_validation["model_artifact_sha256"]):
        raise ValueError("validation/test model experiment identities disagree")
    baseline_test = _read_strict_json(directory / "test-metrics.json", 8*1024*1024)
    if baseline_test.get("evaluation_sha256") != verified_test["baseline_evaluation_sha256"]:
        raise ValueError("test report checksum identity differs from verified experiment")
    test = _replay_partition(plan, sources, model, "test", baseline_test)
    _check_original(test, original, baseline_test)
    test_selected = _compare(test, selected)
    result = {
        "threshold_calibration_version": CALIBRATION_VERSION,
        "source": "synthetic_only", "method": "validation_empirical_FPR_budget",
        "original_model_unchanged": True, "no_test_labels_used_for_selection": True,
        "original_model_sha256": model["model_sha256"],
        "model_artifact_sha256": verified_validation["model_artifact_sha256"],
        "feature_pipeline_sha256": model["feature_processing"]["pipeline_sha256"],
        "experiment_sha256": verified_validation["experiment_sha256"],
        "split_plan_sha256": plan["plan_sha256"],
        "train_groups": plan["partitions"]["train"]["group_ids"],
        "validation_groups": plan["partitions"]["validation"]["group_ids"],
        "test_groups": plan["partitions"]["test"]["group_ids"],
        "source_provenance": {
            "validation": baseline_validation["source_provenance"],
            "test": baseline_test["source_provenance"],
        },
        "original_training_threshold": original, "selection": choice,
        "validation": {
            "comparison_cohort": baseline_validation["comparison_cohort"],
            "original_training_threshold": baseline_validation["overall"],
            "selected_threshold": validation_selected,
            "tradeoff_curve": curve,
            "source_evaluation_sha256": baseline_validation["evaluation_sha256"],
        },
        "test_after_selection": {
            "comparison_cohort": baseline_test["comparison_cohort"],
            "original_training_threshold": baseline_test["overall"],
            "selected_threshold": test_selected,
            "source_evaluation_sha256": baseline_test["evaluation_sha256"],
            "note": "test results are a final held-out audit, never used in cutoff choice",
        },
        "environment": {
            "python": ".".join(str(x) for x in sys.version_info[:3]),
            "implementation": platform.python_implementation(),
            "tool": "motorpulse.calibration",
            "tool_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runtime_dependencies": [],
        },
        "limitations": (
            "Empirical validation FPR is not a guarantee on fresh synthetic runs or physical motors. "
            "False alarms/hour is computed from eligible simulated negative-window exposure. "
            "Validation threshold choice uses scripted synthetic healthy/fault truth and may overfit "
            "this generator and validation sample. AP ranks scores, so does not change with threshold. "
            "Rules remain unchanged and sensor missing/outlier windows abstain for both methods. "
            "No real field reliability, calibrated failure probability, maintenance lead time or RUL."
        ),
    }
    result["threshold_calibration_sha256"] = _hash(result)
    return result


def markdown(report: dict) -> str:
    if report.get("threshold_calibration_version") != CALIBRATION_VERSION:
        raise ValueError("unsupported MP-038 calibration report")
    choice = report["selection"]
    lines = [
        "# MotorPulse AI — Validation-only anomaly cutoff (MP-038)", "",
        f"**Original training threshold:** {report['original_training_threshold']}",
        f"**Validation-selected threshold:** {choice['threshold']}",
        f"**Target validation FPR:** {choice['target_false_positive_rate']}",
        f"**Achieved empirical validation FPR:** {choice['achieved_validation_false_positive_rate']}",
        f"**Validation eligible negatives:** {choice['validation_eligible_negative_windows']}",
        f"**Model identity:** \`{report['original_model_sha256']}\`",
        f"**MP-030 split:** \`{report['split_plan_sha256']}\`", "",
        "**Selection uses ONLY validation eligible negatives; test labels are read afterward.**", "",
        "| Partition | Decision | TP | FP | TN | FN | Recall | FPR | FP/simulated negative hour |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    def fmt(x: Any) -> str:
        return "undefined" if x is None else str(round(x, 6)) if isinstance(x, float) else str(x)
    for partition in ("validation", "test_after_selection"):
        for kind in ("original_training_threshold", "selected_threshold"):
            method = report[partition][kind]["model"]
            lines.append(
                f"| {partition} | {kind} | {method['tp']} | {method['fp']} | {method['tn']} | "
                f"{method['fn']} | {fmt(method['recall'])} | {fmt(method['false_positive_rate'])} | "
                f"{fmt(method['false_alarms_per_simulated_negative_hour'])} |"
            )
    lines += ["", "## Validation-only operating-point tradeoffs", "",
              "| Threshold | TP | FP | Recall | Precision | FPR |", "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for point in report["validation"]["tradeoff_curve"]:
        m = point["validation"]
        lines.append(
            f"| {fmt(point['threshold'])} | {m['tp']} | {m['fp']} | "
            f"{fmt(m['recall'])} | {fmt(m['precision'])} | {fmt(m['false_positive_rate'])} |"
        )
    lines += ["", "## Scientific constraints", "", report["limitations"], "",
              "Threshold is a separate research operating point; the source-trained portable "
              "MP-035 artifact and its embedded threshold remain unchanged. "
              "The untouched test partition is not used for selection. "
              "The validation curve is representative, not exhaustive, "
              "and neither validation FPR nor test FPR establishes industrial guarantees.", ""]
    return "\n".join(lines)


def save_report(report: dict, json_path: str | Path, md_path: str | Path) -> None:
    """Write-once with preflight and rollback of only the new JSON output."""
    if report.get("threshold_calibration_sha256") != _hash(
        {k:v for k,v in report.items() if k != "threshold_calibration_sha256"}
    ):
        raise ValueError("calibration report checksum mismatch")
    jp, mp = Path(json_path), Path(md_path)
    if jp == mp or any(p.exists() or p.is_symlink() or not p.parent.is_dir()
                      or p.parent.is_symlink() for p in (jp, mp)):
        raise ValueError("report needs two unused paths with real, existing parents")
    created = False
    try:
        write_local_manifest(jp, report)
        created = True
        _write_markdown(mp, markdown(report))
    except BaseException:
        if created:
            jp.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validation-only synthetic anomaly threshold research (MP-038)")
    parser.add_argument("--experiment-dir", required=True, type=Path,
                        help="existing fully verified MP-033 experiment directory")
    parser.add_argument("--target-fpr", type=float, default=.05,
                        help="empirical validation FPR budget 0-1; default 0.05")
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = calibrate_experiment(args.experiment_dir, target_fpr=args.target_fpr)
        save_report(report, args.out_json, args.out_md)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Validation-only synthetic cutoff: {report['selection']['threshold']:.6g} "
          f"(report={args.out_json})")


if __name__ == "__main__":
    main()
