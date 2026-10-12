"""MP-036: frozen-model robustness slices on source-verified synthetic holdout runs.

Labels describe programmed simulator settings, not physical stress experiments,
independent datasets, causal effects, or demonstrated field reliability.
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
from .evaluation import EVAL_PARTITIONS, RULE_ALERTS, _episodes, _truth, confusion, evaluate
from .experiment import _sha_file, _write_markdown, validate_experiment_config
from .feature_pipeline import validate_window_contract
from .ims import _read_strict_json, write_local_manifest
from .model_artifact import load_model_artifact
from .splits import _hash

ROBUSTNESS_VERSION = "1.0.0"
MAX_REPORT_BYTES = 8 * 1024 * 1024
TRACK_DIMENSIONS = (
    "speed_variation", "load_variation", "vibration_noise", "sensor_drift",
    "joint_operating_regime", "configured_fault", "configured_strength",
    "progression", "onset_timing",
)
WINDOW_DIMENSIONS = ("effective_fault", "effective_strength", "fault_phase", "sensor_quality")
DIMENSIONS = TRACK_DIMENSIONS + WINDOW_DIMENSIONS


def _range_bucket(value: Any, *, name: str, low: float, high: float) -> str:
    if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
        raise ValueError(f"invalid synthetic {name}")
    if value == 0:
        return "none"
    return "low" if abs(value) <= high / 2 else "high"


def stress_labels(event: dict) -> dict[str, str]:
    """Use source event metadata; never infer a stress condition from scores."""
    cfg = event.get("operating_config")
    if type(cfg) is not dict or set(cfg) != {
        "speed_variation_pct", "load_variation_pct", "sensor_noise_g",
        "sensor_drift_g_per_tick",
    }:
        raise ValueError("unexpected simulator operating_config contract")
    speed = _range_bucket(cfg["speed_variation_pct"], name="speed", low=0, high=.2)
    load = _range_bucket(cfg["load_variation_pct"], name="load", low=0, high=.3)
    noise = _range_bucket(cfg["sensor_noise_g"], name="noise", low=0, high=.1)
    drift = _range_bucket(cfg["sensor_drift_g_per_tick"], name="drift", low=-.001, high=.001)
    if drift != "none":
        drift = ("negative_" if cfg["sensor_drift_g_per_tick"] < 0 else "positive_") + drift
    positive, scenario = _truth(event)
    severity = event.get("severity")
    strength = event.get("configured_severity")
    for name, value in (("severity", severity), ("configured_severity", strength)):
        if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"invalid {name}")
    if (positive and severity <= 0) or (not positive and severity != 0):
        raise ValueError("effective severity contradicts synthetic fault truth")
    configured = event.get("configured_scenario")
    if configured not in ("healthy", "imbalance", "bearing_wear", "misalignment", "overload"):
        raise ValueError("invalid configured synthetic fault")
    if configured == "healthy" and strength != 0:
        raise ValueError("healthy configured fault must have zero strength")
    progression = event.get("progression")
    if progression not in ("constant", "linear", "exponential"):
        raise ValueError("invalid programmed progression")
    quality = event.get("sensor_quality")
    if quality not in ("good", "missing", "outlier"):
        raise ValueError("unknown sensor quality")
    tick, onset = event.get("tick"), event.get("onset_tick")
    if type(tick) is not int or type(onset) is not int or tick < 1 or onset < 1:
        raise ValueError("invalid programmed onset tick")
    def strength_bin(value: float) -> str:
        return "healthy" if value == 0 else "low" if value <= 1/3 else "medium" if value <= 2/3 else "high"
    return {
        "speed_variation": speed, "load_variation": load,
        "vibration_noise": noise, "sensor_drift": drift,
        "joint_operating_regime": "speed_" + speed + "__load_" + load,
        "configured_fault": configured, "configured_strength": strength_bin(strength),
        "progression": progression,
        "onset_timing": "onset_at_first_tick" if onset == 1 else "onset_later",
        "effective_fault": scenario, "effective_strength": strength_bin(severity),
        "fault_phase": event.get("fault_phase"), "sensor_quality": quality,
    }


def _metrics(rows: list[dict], decision: str) -> dict:
    result = confusion(rows, decision=decision, with_ap=decision == "anomaly_alert")
    exposure = sum(r["step_seconds"] for r in rows if not r["positive"])
    result["false_alarms_per_simulated_negative_hour"] = (
        result["fp"] * 3600 / exposure if exposure > 0 else None
    )
    return result


def _delays(tracks: dict[tuple[str, str], list[dict]]) -> dict:
    episodes = []
    for rows in tracks.values():
        episodes.extend(_episodes(rows, rows[0]["step_seconds"])["details"])
    delays = sorted(e["delay_seconds"] for e in episodes if e["delay_seconds"] is not None)
    n = len(delays)
    return {
        "episodes": len(episodes), "detected": n, "missed": len(episodes) - n,
        "abstained_only": sum(e["no_eligible_fault_windows"] for e in episodes),
        "mean_delay_seconds": sum(delays)/n if n else None,
        "median_delay_seconds": (delays[(n-1)//2] + delays[n//2])/2 if n else None,
        "note": "first observed synthetic effective fault tick; no physical failure lead time; incomplete end episodes may be censored",
    }


def summarize_stress_rows(rows: list[dict]) -> dict:
    """Separate same-cohort comparisons; window slices must not invent onsets."""
    tracks: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        tracks[(r["group_id"], r["asset_id"])].append(r)
    for key, group in tracks.items():
        ticks = [r["tick"] for r in group]
        if ticks != list(range(1, len(group)+1)):
            raise ValueError(f"incomplete or out-of-order track {key}")
        if len({r["step_seconds"] for r in group}) != 1:
            raise ValueError("simulated step changed within a track")
        for dimension in TRACK_DIMENSIONS:
            if len({r["stress"][dimension] for r in group}) != 1:
                raise ValueError("a track-level stress condition changed mid-run")
    buckets = {}
    for dimension in DIMENSIONS:
        values = sorted({r["stress"][dimension] for r in rows})
        members = {}
        for value in values:
            selected = [r for r in rows if r["stress"][dimension] == value]
            eligible = [r for r in selected if r["eligible"]]
            qualities = dict(sorted(Counter(r["quality"] for r in selected if not r["eligible"]).items()))
            subset = {
                "total_windows": len(selected), "eligible_both_methods": len(eligible),
                "excluded_both_methods": len(selected)-len(eligible),
                "abstentions": qualities,
                "source_groups": sorted({r["group_id"] for r in selected}),
                "tracks": len({(r["group_id"],r["asset_id"]) for r in selected}),
                "model": _metrics(eligible, "anomaly_alert"),
                "rules": _metrics(eligible, "rule_alert"),
            }
            if dimension in TRACK_DIMENSIONS:
                owned_tracks = {
                    key: group for key, group in tracks.items()
                    if group[0]["stress"][dimension] == value
                }
                subset["detection_episodes"] = _delays(owned_tracks)
            else:
                subset["detection_episodes"] = None
                subset["delay_note"] = "not computed from window-filtered tracks, which could invent new onset episodes"
            members[value] = subset
        buckets[dimension] = members
    eligible = [r for r in rows if r["eligible"]]
    return {
        "coverage": {
            "total_windows": len(rows), "eligible_both_methods": len(eligible),
            "abstentions": dict(sorted(Counter(r["quality"] for r in rows if not r["eligible"]).items())),
        },
        "overall": {"model": _metrics(eligible, "anomaly_alert"),
                    "rules": _metrics(eligible, "rule_alert")},
        "by_stress": buckets,
        "detection_episodes": _delays(tracks),
    }


def assess_robustness(plan: dict, manifests: list[Path], artifact_path: Path, *,
                      partition: str = "test") -> dict:
    """Reverify MP-035 model + MP-011 baseline before any stress aggregation."""
    if partition not in EVAL_PARTITIONS:
        raise ValueError("only validation or test holdouts may be assessed")
    model = load_model_artifact(artifact_path, plan=plan, manifests=manifests)
    baseline = evaluate(plan, manifests, model, partition=partition, max_events=0)
    sources = _validated_sources(plan, manifests)
    threshold = model["calibration"]["threshold"]
    rows = []
    for group_id in sorted(plan["partitions"][partition]["group_ids"]):
        source = sources[group_id]
        for event in _events(source):
            validate_window_contract(event)
            labels = stress_labels(event)
            positive, _ = _truth(event)
            quality = event["sensor_quality"]
            health = event.get("health")
            if (quality == "good" and health not in ("normal", *RULE_ALERTS)) or (
                quality == "missing" and health != "unavailable"
            ) or (quality == "outlier" and health != "suspect"):
                raise ValueError("sensor quality and rule health disagree")
            eligible = quality == "good"
            score = _score(_vector(event), model["center"], model["effective_scales"]) if eligible else None
            if score is not None and not isfinite(score):
                raise ValueError("nonfinite synthetic score")
            rows.append({
                "group_id": group_id, "asset_id": event["asset_id"],
                "tick": event["tick"], "step_seconds": source["step_seconds"],
                "scenario": event["scenario"], "timestamp_utc": event["timestamp_utc"],
                "positive": positive, "eligible": eligible, "quality": quality,
                "score": score, "anomaly_alert": score > threshold if eligible else False,
                "rule_alert": health in RULE_ALERTS if eligible else False,
                "stress": labels,
            })
    summary = summarize_stress_rows(rows)
    episodes = summary["detection_episodes"]
    expected = baseline["detection_episodes"]
    if (summary["overall"] != baseline["overall"] or
            summary["coverage"]["total_windows"] != baseline["comparison_cohort"]["total_windows"] or
            summary["coverage"]["eligible_both_methods"] != baseline["comparison_cohort"]["eligible_both_methods"] or
            summary["coverage"]["abstentions"] != baseline["comparison_cohort"]["abstentions"] or
            {k:episodes[k] for k in ("detected","missed","abstained_only","mean_delay_seconds","median_delay_seconds")} !=
            {k:expected[k] for k in ("detected","missed","abstained_only","mean_delay_seconds","median_delay_seconds")} or
            episodes["episodes"] != expected["total"]):
        raise ValueError("MP-036 aggregates disagree with original MP-011 evaluation")
    report = {
        "robustness_version": ROBUSTNESS_VERSION, "source": "synthetic_only",
        "partition": partition, "whole_run_heldout": True,
        "split_plan_sha256": plan["plan_sha256"],
        "model_sha256": model["model_sha256"],
        "model_artifact_sha256": _read_strict_json(artifact_path, 512*1024)["artifact_sha256"],
        "processor_sha256": model["feature_processing"]["pipeline_sha256"],
        "fixed_training_threshold": threshold, "frozen_fit_partition": "train",
        "baseline_evaluation_sha256": baseline["evaluation_sha256"],
        "source_provenance": baseline["source_provenance"],
        "training_groups": baseline["training_groups"],
        "heldout_groups": baseline["evaluated_groups"],
        "stress_matrix": {
            "dimensions": list(DIMENSIONS),
            "grouping_note": "programmed event-level labels; assets within a generator run are correlated; bins overlap across dimensions",
            "strength_bins": "healthy=0, low=(0,1/3], medium=(1/3,2/3], high=(2/3,1]",
            "variation_bins": "none=0; low=(0,max/2], high=(max/2,max]; drift sign retained",
            "source_dataset": "MotorPulse-AI synthetic simulator only; no independent IMS or CWRU results",
        },
        **summary,
        "environment": {
            "python": ".".join(map(str, sys.version_info[:3])),
            "implementation": platform.python_implementation(),
            "tool": "motorpulse.robustness",
            "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runtime_dependencies": [],
        },
        "limitations": (
            "Controlled synthetic regime slices, not intervention-based or cross-domain validation. "
            "Correlated seeded generator runs and changing class composition can confound comparisons. "
            "False alarms per negative exposure hour use virtual simulated time. "
            "Undefined metric denominators are null. No real-world diagnostic reliability, "
            "calibrated failure probability, physical maintenance lead time or RUL."
        ),
    }
    report["robustness_sha256"] = _hash(report)
    return report


def from_experiment(root: str | Path, *, partition: str = "test") -> dict:
    """Consume original MP-033 artifact/index and complete local source runs."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("experiment directory must be a local nonsymlink directory")
    index = _read_strict_json(root / "experiment-index.json", MAX_REPORT_BYTES)
    if _hash({k: v for k, v in index.items() if k != "experiment_sha256"}) != index.get("experiment_sha256"):
        raise ValueError("experiment index checksum mismatch")
    config = validate_experiment_config(_read_strict_json(root / "experiment-config.json", 65536))
    if _hash(config) != index.get("config_sha256"):
        raise ValueError("experiment configuration differs from index")
    checks = index.get("stable_artifact_sha256")
    if type(checks) is not dict or not checks:
        raise ValueError("missing experiment file integrity index")
    for name, digest in checks.items():
        if (type(name) is not str or len(name) > 128 or
                not all(part not in ("", ".", "..") for part in name.split("/")) or
                not (name.startswith("runs/seed-") or name in {
                    "experiment-config.json", "split-plan.json", "trained-model.json",
                    "model-artifact.json", "validation-metrics.json", "test-metrics.json", "SUMMARY.md"
                })):
            raise ValueError("invalid experiment artifact path")
        path = root / name
        if any(p.is_symlink() for p in (path, *list(path.parents)[:2])) or not path.is_file() or _sha_file(path) != digest:
            raise ValueError("experiment artifact bytes differ from index")
    manifests = [root / "runs" / f"seed-{seed:010d}" / "manifest.json" for seed in config["seeds"]]
    plan = _read_strict_json(root / "split-plan.json", 256*1024)
    report = assess_robustness(plan, manifests, root / "model-artifact.json", partition=partition)
    if report["baseline_evaluation_sha256"] != index["evaluation_sha256"][partition]:
        raise ValueError("baseline evaluation identity disagrees with experiment index")
    report["experiment_sha256"] = index["experiment_sha256"]
    report["robustness_sha256"] = _hash({k:v for k,v in report.items() if k != "robustness_sha256"})
    return report


def markdown(report: dict) -> str:
    if report.get("robustness_version") != ROBUSTNESS_VERSION:
        raise ValueError("unsupported MP-036 report")
    lines = [
        "# MotorPulse AI — Simulated regime robustness", "",
        f"Partition: {report['partition']} (complete held-out source runs)",
        f"Frozen model SHA-256: {report['model_sha256']}",
        f"Verified model artifact SHA-256: {report['model_artifact_sha256']}",
        f"MP-030 split SHA-256: {report['split_plan_sha256']}", "",
        "Both methods share exactly the same good-sensor cohort.",
        "Undefined means no valid denominator; sensor abstentions are never healthy machine predictions.", "",
        "| Stress dimension | Condition | Total | Eligible | Model FP | Rule FP | Model recall | Rule recall |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    def fmt(value: Any) -> str:
        return "undefined" if value is None else str(round(value, 5)) if isinstance(value, float) else str(value)
    for dimension, buckets in report["by_stress"].items():
        for name, cohort in buckets.items():
            m, r = cohort["model"], cohort["rules"]
            lines.append(f"| {dimension} | {name} | {cohort['total_windows']} | {cohort['eligible_both_methods']} | {m['fp']} | {r['fp']} | {fmt(m['recall'])} | {fmt(r['recall'])} |")
    lines += ["", "## Scientific limitations", "", report["limitations"], "",
              "Different bins have different sample sizes and class mixes; these comparisons are descriptive, not causal.",
              "No real IMS readings, calibrated failure probability, physical lead time or RUL.", ""]
    return "\n".join(lines)


def save_report(report: dict, json_path: str | Path, md_path: str | Path) -> None:
    """Exclusive dual-output; roll back only a newly created JSON file on failure."""
    jp, mp = Path(json_path), Path(md_path)
    if jp == mp or any(p.exists() or p.is_symlink() or p.parent.is_symlink() or not p.parent.is_dir()
                       for p in (jp, mp)):
        raise ValueError("report outputs must be two unused paths with real existing parents")
    written = False
    try:
        write_local_manifest(jp, report)
        written = True
        _write_markdown(mp, markdown(report))
    except BaseException:
        if written:
            jp.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="MP-036 verified frozen-model synthetic regime robustness")
    parser.add_argument("--experiment-dir", required=True, type=Path, help="existing MP-033 output directory")
    parser.add_argument("--partition", choices=EVAL_PARTITIONS, default="test")
    parser.add_argument("--out-json", required=True, type=Path, help="new JSON file, never overwrite")
    parser.add_argument("--out-md", required=True, type=Path, help="new Markdown file, never overwrite")
    args = parser.parse_args()
    try:
        report = from_experiment(args.experiment_dir, partition=args.partition)
        save_report(report, args.out_json, args.out_md)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Synthetic held-out robustness saved: {args.out_json} ({report['robustness_sha256'][:16]})")


if __name__ == "__main__":
    main()
