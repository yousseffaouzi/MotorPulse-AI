"""MP-037: explainable, same-window synthetic rule/ML comparison.

The only supported entry point loads a verified MP-033 experiment and MP-035
model artifact. Examples describe numeric decisions, not causes or prognoses.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from math import isclose, isfinite
from pathlib import Path
import platform
import sys
from typing import Any

from .anomaly import FEATURES, FEATURE_UNITS, _events, _score, _validated_sources, _vector
from .evaluation import EVAL_PARTITIONS, RULE_ALERTS, _truth
from .experiment import MAX_CONFIG_BYTES, _write_markdown, validate_experiment_config
from .feature_pipeline import validate_window_contract
from .ims import _read_strict_json, write_local_manifest
from .model_artifact import load_model_artifact
from .robustness import _metrics, from_experiment as verified_robustness
from .scenarios import SCENARIOS
from .sim import classify
from .splits import _hash

COMPARISON_VERSION = "1.0.0"
MAX_EXAMPLES = 12
OUTCOMES = (
    "model_only_false_positive",
    "rules_only_false_positive",
    "shared_false_positive",
    "model_only_true_positive",
    "rules_only_true_positive",
    "shared_true_positive",
    "shared_false_negative",
    "shared_true_negative",
    "sensor_abstention",
)
RULE_CHECKS = (
    ("elevated_rms", "rms_g", ">=", .36),
    ("high_temperature", "temperature_c", ">=", 82.0),
    ("impulsive_waveform", "crest_factor", ">=", 2.7),
    ("critical_rms", "rms_g", ">=", .55),
    ("critical_temperature", "temperature_c", ">=", 92.0),
)


def _outcome(positive: bool, eligible: bool, anomaly: bool, rules: bool) -> str:
    if not eligible:
        return "sensor_abstention"
    if positive:
        if anomaly and rules:
            return "shared_true_positive"
        if anomaly:
            return "model_only_true_positive"
        if rules:
            return "rules_only_true_positive"
        return "shared_false_negative"
    if anomaly and rules:
        return "shared_false_positive"
    if anomaly:
        return "model_only_false_positive"
    if rules:
        return "rules_only_false_positive"
    return "shared_true_negative"


def _rule_explanation(event: dict, eligible: bool) -> dict:
    health, reasons = event.get("health"), event.get("reasons")
    if type(reasons) is not list or any(type(r) is not str for r in reasons):
        raise ValueError("synthetic rule reasons must be a list of strings")
    if not eligible:
        expected = "unavailable" if event["sensor_quality"] == "missing" else "suspect"
        if health != expected or not reasons:
            raise ValueError("sensor abstention and source health disagree")
        return {
            "decision": "abstain", "health": health, "reasons": reasons,
            "triggered_checks": [], "checked_thresholds": [],
            "note": "machine rules suppressed for simulated missing/outlier sensor",
        }
    values = _vector(event)  # validates the complete allowlisted model input
    rms, temp, crest = (event[k] for k in ("rms_g", "temperature_c", "crest_factor"))
    calculated_health, calculated_reasons = classify(rms, temp, crest)
    if health != calculated_health or reasons != calculated_reasons:
        raise ValueError("source rule health/reasons disagree with independent MP-003 rules")
    checks = [
        {"name": name, "feature": feature, "operator": operator,
         "threshold": threshold, "triggered": bool(
             value >= threshold and (
                 name != "impulsive_waveform" or rms >= .20
             )),
         "secondary_rms_min_g": .20 if name == "impulsive_waveform" else None}
        for name, feature, operator, threshold in RULE_CHECKS
        for value in (event[feature],)
    ]
    return {
        "decision": "alert" if health in RULE_ALERTS else "normal",
        "health": health, "reasons": reasons,
        "triggered_checks": [c["name"] for c in checks if c["triggered"]],
        "checked_thresholds": checks,
        "note": "fixed illustrative simulator thresholds, not industrial standards",
    }


def _model_explanation(event: dict, model: dict, eligible: bool) -> dict:
    threshold = model["calibration"]["threshold"]
    if not eligible:
        return {
            "decision": "unscorable", "score": None, "threshold": threshold,
            "margin_above_threshold": None, "contributions": [],
            "note": "sensor missing or suspect: not a healthy-model prediction",
        }
    vector = _vector(event)
    terms = []
    squares = []
    for name, unit, value, mean, scale in zip(
        FEATURES, FEATURE_UNITS, vector, model["center"], model["effective_scales"]
    ):
        standardized = (value - mean)/scale
        square = standardized * standardized
        squares.append(square)
        terms.append({
            "feature": name, "unit": unit, "observed": value,
            "training_center": mean, "training_scale": scale,
            "signed_standardized_deviation": standardized,
            "squared_distance_contribution": square / len(FEATURES),
        })
    score = _score(vector, model["center"], model["effective_scales"])
    if not isfinite(score):
        raise ValueError("model produced nonfinite synthetic score")
    distance_sum = sum(squares)
    for term, square in zip(terms, squares):
        term["fraction_of_score_squared"] = square / distance_sum if distance_sum else 0.0
    if not isclose(
        sum(t["squared_distance_contribution"] for t in terms),
        score * score, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise ValueError("feature contributions do not reproduce frozen model score")
    return {
        "decision": "anomaly" if score > threshold else "within_threshold",
        "score": score, "threshold": threshold,
        "margin_above_threshold": score-threshold, "contributions": terms,
        "note": "noncausal standardized distance accounting, not probabilities or learned feature importance",
    }


def explain_window(event: dict, model: dict, *, group_id: str) -> dict:
    """An explanatory view for one *already source-verified* simulator event.

    Calling this helper alone is not provenance verification; use
    compare_experiment for a verified complete-partition report.
    """
    validate_window_contract(event)
    positive, effective = _truth(event)
    quality = event.get("sensor_quality")
    if quality not in ("good", "missing", "outlier"):
        raise ValueError("unknown sensor-quality state")
    configured = event.get("configured_scenario")
    if configured not in SCENARIOS:
        raise ValueError("unknown configured synthetic scenario")
    eligible = quality == "good"
    rule = _rule_explanation(event, eligible)
    ml = _model_explanation(event, model, eligible)
    ml_alert = ml["decision"] == "anomaly"
    rule_alert = rule["decision"] == "alert"
    outcome = _outcome(positive, eligible, ml_alert, rule_alert)
    for key in ("asset_id", "timestamp_utc", "event_id", "export_id"):
        if type(event.get(key)) is not str or not event[key]:
            raise ValueError(f"missing source event {key}")
    return {
        "group_id": group_id, "source_id": event["export_id"],
        "event_id": event["event_id"], "asset_id": event["asset_id"],
        "tick": event["tick"], "timestamp_utc": event["timestamp_utc"],
        "effective_synthetic_truth": effective, "configured_future_or_active_fault": configured,
        "fault_phase": event["fault_phase"], "sensor_quality": quality,
        "eligible": eligible, "synthetic_fault_positive": positive,
        "outcome": outcome, "model": ml, "rules": rule,
    }


def _summary(rows: list[dict], samples: dict[str, list[dict]], baseline: dict) -> dict:
    eligible = [r for r in rows if r["eligible"]]
    overall = {
        "model": _metrics(eligible, "anomaly_alert"),
        "rules": _metrics(eligible, "rule_alert"),
    }
    if overall != baseline["overall"]:
        raise ValueError("MP-037 rule/model metrics disagree with MP-011")
    if (len(rows) != baseline["comparison_cohort"]["total_windows"] or
            len(eligible) != baseline["comparison_cohort"]["eligible_both_methods"]):
        raise ValueError("MP-037 cohort differs from MP-011")
    abstentions = dict(sorted(Counter(r["quality"] for r in rows if not r["eligible"]).items()))
    if abstentions != baseline["comparison_cohort"]["abstentions"]:
        raise ValueError("MP-037 abstentions differ from MP-011")
    if set(r["group_id"] for r in rows) != set(baseline["evaluated_groups"]):
        raise ValueError("MP-037 source groups differ from MP-011")
    for group, measures in baseline["by_run"].items():
        group_rows = [r for r in eligible if r["group_id"] == group]
        if {method: _metrics(group_rows, column)
            for method, column in (("model", "anomaly_alert"), ("rules", "rule_alert"))} != measures:
            raise ValueError("MP-037 per-run metrics differ from MP-011")
    categories = Counter(r["outcome"] for r in rows)
    if sum(categories.values()) != len(rows) or any(key not in OUTCOMES for key in categories):
        raise ValueError("unaccounted decision outcome")
    if (sum(categories.get(k, 0) for k in OUTCOMES if k != "sensor_abstention") != len(eligible)
            or categories.get("sensor_abstention", 0) != len(rows)-len(eligible)):
        raise ValueError("disagreement categories do not cover complete cohort")
    if (overall["model"]["fp"] !=
            categories["model_only_false_positive"] + categories["shared_false_positive"] or
            overall["rules"]["fp"] !=
            categories["rules_only_false_positive"] + categories["shared_false_positive"] or
            overall["model"]["fn"] !=
            categories["rules_only_true_positive"] + categories["shared_false_negative"] or
            overall["rules"]["fn"] !=
            categories["model_only_true_positive"] + categories["shared_false_negative"]):
        raise ValueError("false-positive/negative disagreement does not match confusion matrix")
    return {
        "comparison_cohort": {
            "total_windows": len(rows), "eligible_both_methods": len(eligible),
            "abstentions": abstentions, "excluded_from_both_metrics": len(rows)-len(eligible),
        },
        "overall": overall,
        "agreement": {
            "both_alert": sum(r["anomaly_alert"] and r["rule_alert"] for r in eligible),
            "model_only": sum(r["anomaly_alert"] and not r["rule_alert"] for r in eligible),
            "rules_only": sum(r["rule_alert"] and not r["anomaly_alert"] for r in eligible),
            "neither_alert": sum(not r["anomaly_alert"] and not r["rule_alert"] for r in eligible),
            "abstained": len(rows)-len(eligible),
        },
        "outcome_counts": {key: categories[key] for key in OUTCOMES},
        "examples": samples,
    }


def compare_experiment(root: str | Path, *, partition: str = "test",
                       max_examples: int = 4) -> dict:
    """Compute explanations for entire verified partition; retain bounded examples."""
    if partition not in EVAL_PARTITIONS:
        raise ValueError("only validation or test held-out runs are permitted")
    if type(max_examples) is not int or not 0 <= max_examples <= MAX_EXAMPLES:
        raise ValueError(f"max_examples must be in [0, {MAX_EXAMPLES}]")
    directory = Path(root)
    # MP-036 fully checks experiment-index integrity, original MP-035 artifact,
    # dataset cards and the MP-011 evaluation before any explanations.
    verified = verified_robustness(directory, partition=partition)
    cfg = validate_experiment_config(_read_strict_json(
        directory / "experiment-config.json", MAX_CONFIG_BYTES))
    plan = _read_strict_json(directory / "split-plan.json", 256 * 1024)
    manifests = [directory / "runs" / f"seed-{seed:010d}" / "manifest.json"
                 for seed in cfg["seeds"]]
    model = load_model_artifact(directory / "model-artifact.json",
                                plan=plan, manifests=manifests)
    sources = _validated_sources(plan, manifests)
    baseline = _read_strict_json(directory / f"{partition}-metrics.json", 8 * 1024 * 1024)
    if baseline.get("evaluation_sha256") != verified["baseline_evaluation_sha256"]:
        raise ValueError("MP-011 evaluation identity differs from verified experiment")
    if (baseline["trained_model_sha256"] != model["model_sha256"] or
            baseline["threshold_fixed_from_training"] != model["calibration"]["threshold"] or
            baseline["split_plan_sha256"] != plan["plan_sha256"]):
        raise ValueError("MP-011 fixed model and split identities disagree")
    examples = {key: [] for key in OUTCOMES}
    rows = []
    for group_id in sorted(plan["partitions"][partition]["group_ids"]):
        source = sources[group_id]
        for event in _events(source):
            explained = explain_window(event, model, group_id=group_id)
            alert = explained["model"]["decision"] == "anomaly"
            rule = explained["rules"]["decision"] == "alert"
            rows.append({
                "group_id": group_id, "asset_id": explained["asset_id"],
                "positive": explained["synthetic_fault_positive"],
                "eligible": explained["eligible"], "quality": explained["sensor_quality"],
                "anomaly_alert": alert, "rule_alert": rule,
                "score": explained["model"]["score"], "step_seconds": source["step_seconds"],
                "outcome": explained["outcome"],
            })
            group = examples[explained["outcome"]]
            if len(group) < max_examples:
                group.append(explained)
    summary = _summary(rows, examples, baseline)
    if (summary["overall"] != verified["overall"] or
            summary["comparison_cohort"]["total_windows"] != verified["coverage"]["total_windows"] or
            summary["comparison_cohort"]["abstentions"] != verified["coverage"]["abstentions"]):
        raise ValueError("MP-037 and MP-036 disagree on verified held-out cohort")
    report = {
        "comparison_version": COMPARISON_VERSION, "source": "synthetic_only",
        "partition": partition, "whole_run_heldout": True,
        "experiment_sha256": verified["experiment_sha256"],
        "split_plan_sha256": plan["plan_sha256"],
        "model_sha256": model["model_sha256"],
        "model_artifact_sha256": verified["model_artifact_sha256"],
        "feature_pipeline_sha256": model["feature_processing"]["pipeline_sha256"],
        "baseline_evaluation_sha256": baseline["evaluation_sha256"],
        "frozen_training_threshold": model["calibration"]["threshold"],
        "training_groups": baseline["training_groups"],
        "evaluated_groups": baseline["evaluated_groups"],
        "source_provenance": baseline["source_provenance"],
        **summary,
        "example_selection": {
            "policy": "first N per outcome in sorted source-group and original JSONL event order",
            "max_per_outcome": max_examples,
            "examples_are_representative": False,
            "total_scored_windows": len(rows),
        },
        "score_explanation": (
            "score=sqrt(sum(((observed-training_center)/training_scale)^2)/5); "
            "five allowlisted features and their nonnegative squared contributions "
            "explain arithmetic distance, not causation or calibrated probabilities."
        ),
        "label_note": (
            "effective scripted synthetic scenario is the evaluation truth; "
            "configured future faults are not positives before activation."
        ),
        "scientific_limit": (
            "Educational synthetic generator only. No independent field measurement, "
            "industrial false-positive rate, failure diagnosis, calibrated risk, "
            "maintenance lead time, or remaining useful life. Sensor missing/outlier "
            "windows abstain for BOTH methods."
        ),
        "environment": {
            "python": ".".join(str(x) for x in sys.version_info[:3]),
            "implementation": platform.python_implementation(),
            "tool": "motorpulse.comparison",
            "tool_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runtime_dependencies": [],
        },
    }
    report["comparison_sha256"] = _hash(report)
    return report


def markdown(report: dict) -> str:
    """Bounded, portable human-readable explanations (not an HTML dashboard)."""
    if report.get("comparison_version") != COMPARISON_VERSION:
        raise ValueError("unsupported comparison report")
    counts = report["outcome_counts"]
    lines = [
        "# MotorPulse AI — Rules versus trained anomaly model (MP-037)", "",
        f"**Held-out partition:** {report['partition']} · **Model:** `{report['model_sha256']}`",
        f"**Verified artifact:** `{report['model_artifact_sha256']}`",
        f"**MP-030 split:** `{report['split_plan_sha256']}`",
        f"**Train-only threshold:** {report['frozen_training_threshold']}", "",
        f"**Same eligible windows:** {report['comparison_cohort']['eligible_both_methods']} / "
        f"{report['comparison_cohort']['total_windows']}; "
        f"**abstentions:** {report['comparison_cohort']['abstentions']}", "",
        "| Metric | Model | Rules |", "| --- | ---: | ---: |",
    ]
    for label, key in (
        ("True positives", "tp"), ("False positives", "fp"),
        ("True negatives", "tn"), ("False negatives", "fn"),
        ("Precision", "precision"), ("Recall", "recall"),
        ("False positive rate", "false_positive_rate"),
        ("Average precision (ranking)", "average_precision"),
        ("False alerts / simulated negative exposure hour", "false_alarms_per_simulated_negative_hour"),
    ):
        def fmt(x: Any) -> str:
            return "undefined" if x is None else str(round(x, 6)) if isinstance(x, float) else str(x)
        lines.append(f"| {label} | {fmt(report['overall']['model'][key])} | "
                     f"{fmt(report['overall']['rules'][key])} |")
    lines += ["", "## Decision outcomes (whole held-out partition)", "",
              "| Outcome | Count |", "| --- | ---: |"]
    for key in OUTCOMES:
        lines.append(f"| {key.replace('_', ' ')} | {counts[key]} |")
    lines += ["", "## Deterministic selected examples", "",
              f"At most {report['example_selection']['max_per_outcome']} first events per "
              "outcome, not a representative or random sample.", ""]
    for outcome in OUTCOMES:
        sample = report["examples"][outcome]
        lines.extend([f"### {outcome.replace('_', ' ').title()} — {counts[outcome]} total", ""])
        if not sample:
            lines.extend(["No selected examples.", ""])
            continue
        for event in sample:
            lines.append(
                f"- **{event['asset_id']}**, run `{event['group_id']}`, tick {event['tick']}: "
                f"effective truth **{event['effective_synthetic_truth']}**, "
                f"configured **{event['configured_future_or_active_fault']}**; "
                f"sensor **{event['sensor_quality']}**; "
                f"ML **{event['model']['decision']}**, rules **{event['rules']['health']}**."
            )
            if event["eligible"]:
                model = event["model"]
                top = sorted(model["contributions"],
                             key=lambda x: -x["squared_distance_contribution"])[:2]
                highlights = ", ".join(
                    f"{x['feature']} (z={x['signed_standardized_deviation']:.3f})" for x in top
                )
                lines.append(
                    f"  - Score {model['score']:.6f} versus frozen threshold "
                    f"{model['threshold']:.6f}; leading arithmetic deviations: {highlights}. "
                    f"Rule triggers: {event['rules']['triggered_checks']}; "
                    f"rule reasons: {event['rules']['reasons']}."
                )
            else:
                lines.append("  - Both methods abstained: no anomaly score or machine-rule decision.")
        lines.append("")
    lines += ["## Interpretation and restrictions", "",
              report["score_explanation"], "",
              report["label_note"], "", report["scientific_limit"], "",
              "Feature contributions only decompose the standardized distance. "
              "They are not learned causal explanations. The listed rule thresholds "
              "are illustrative and do not represent an industrial alarm standard.", ""]
    return "\n".join(lines)


def save_report(report: dict, json_path: str | Path, markdown_path: str | Path) -> None:
    """Exclusive dual output, rolling back only a JSON file owned by this call."""
    if report.get("comparison_sha256") != _hash(
        {k: v for k, v in report.items() if k != "comparison_sha256"}
    ):
        raise ValueError("comparison checksum mismatch")
    json_file, md_file = Path(json_path), Path(markdown_path)
    if (json_file == md_file or
            any(p.exists() or p.is_symlink() or not p.parent.is_dir() or
                p.parent.is_symlink() for p in (json_file, md_file))):
        raise ValueError("choose two new, non-symlink local output files")
    created = False
    try:
        write_local_manifest(json_file, report)
        created = True
        _write_markdown(md_file, markdown(report))
    except BaseException:
        if created:
            json_file.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verified held-out synthetic explanations: original rules vs frozen model")
    parser.add_argument("--experiment-dir", required=True, type=Path,
                        help="existing complete MP-033 experiment directory")
    parser.add_argument("--partition", choices=EVAL_PARTITIONS, default="test")
    parser.add_argument("--max-examples", type=int, default=4,
                        help=f"maximum examples per outcome, 0-{MAX_EXAMPLES}")
    parser.add_argument("--out-json", required=True, type=Path,
                        help="new path for versioned JSON report, never overwrite")
    parser.add_argument("--out-md", required=True, type=Path,
                        help="new path for readable Markdown report, never overwrite")
    args = parser.parse_args()
    try:
        report = compare_experiment(args.experiment_dir, partition=args.partition,
                                    max_examples=args.max_examples)
        save_report(report, args.out_json, args.out_md)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Synthetic comparison: {args.out_json} ({report['comparison_sha256'][:16]})")


if __name__ == "__main__":
    main()
