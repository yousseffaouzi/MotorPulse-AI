"""MP-011: honest, held-out synthetic anomaly and heuristic-rule evaluation.

No model fitting and no IMS readings. Uses verified whole-run MP-030 plans
and the frozen MP-010 model. Missing/outlier readings are abstentions, not
negative classifications. This is NOT measured predictive maintenance.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import Any, Sequence

from .anomaly import FEATURES, FEATURE_UNITS, MODEL_VERSION, _events, _score, _validated_sources, _vector
from .feature_pipeline import validate_window_contract, verify_fitted_preprocessing
from .dataset_cards import synthetic_run_card
from .ims import _read_strict_json, write_local_manifest
from .splits import _hash

FAULTS = ("imbalance", "bearing_wear", "misalignment", "overload")
RULE_ALERTS = ("warning", "critical")
EVAL_PARTITIONS = ("validation", "test")
MAX_REPORT_EVENTS = 30
MAX_EVALUATION_EVENTS = 60000


def average_precision(rows: list[dict]) -> float | None:
    """Non-interpolated AP; group exact score ties before changing recall.

    Returns null if the eligible evaluation cohort lacks either class.
    """
    positives = sum(int(row["positive"]) for row in rows)
    negatives = len(rows) - positives
    if not positives or not negatives:
        return None
    ranked = sorted(rows, key=lambda r: -r["score"])
    tp = fp = 0
    ap = 0.0
    index = 0
    while index < len(ranked):
        end = index
        score = ranked[index]["score"]
        while end < len(ranked) and ranked[end]["score"] == score:
            tp += int(ranked[end]["positive"])
            fp += int(not ranked[end]["positive"])
            end += 1
        increment = sum(int(x["positive"]) for x in ranked[index:end])
        if increment:
            ap += (increment / positives) * (tp / (tp + fp))
        index = end
    return ap


def confusion(rows: list[dict], *, decision: str, step_seconds: float | None = None,
              with_ap: bool = False) -> dict:
    """Calculate counts on a common eligible cohort; undefined => JSON null."""
    if decision not in ("anomaly_alert", "rule_alert"):
        raise ValueError("invalid decision column")
    tp = fp = tn = fn = 0
    for row in rows:
        if type(row.get("positive")) is not bool or type(row.get(decision)) is not bool:
            raise ValueError("binary truth/decision flags required")
        positive, predicted = row["positive"], row[decision]
        if positive and predicted:
            tp += 1
        elif positive:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
    positives = tp + fn
    negatives = tn + fp
    if step_seconds is not None and (type(step_seconds) not in (int, float)
                                     or not isfinite(step_seconds) or step_seconds <= 0):
        raise ValueError("invalid simulated step seconds")
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / positives if positives else None
    specificity = tn / negatives if negatives else None
    fpr = fp / negatives if negatives else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "n": len(rows), "positive_windows": positives, "negative_windows": negatives,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision, "recall": recall, "specificity": specificity,
        "false_positive_rate": fpr, "f1": f1,
        "average_precision": average_precision(rows) if with_ap else None,
        "false_alarms_per_simulated_negative_hour":
            fp * 3600 / (negatives * step_seconds)
            if negatives and step_seconds is not None else None,
        "metric_note": "null denotes undefined denominator or unavailable score ranking",
    }


def _validate_model(model: dict, plan: dict, sources: dict) -> None:
    if type(model) is not dict or model.get("model_version") != MODEL_VERSION or (
        model.get("method") != "healthy_training_zscore_euclidean" or
        model.get("score_direction") != "higher_is_more_unusual" or
        model.get("score_is_failure_probability") is not False or
        model.get("remaining_useful_life") is not None
    ):
        raise ValueError("unsupported trained synthetic model")
    if _hash({k: v for k, v in model.items() if k != "model_sha256"}) != model.get("model_sha256"):
        raise ValueError("trained model checksum mismatch")
    training = model.get("training")
    if type(training) is not dict or (
        training.get("split_plan_sha256") != plan["plan_sha256"] or
        training.get("groups") != sorted(plan["partitions"]["train"]["group_ids"]) or
        training.get("fit_partitions") != ["train"]
    ):
        raise ValueError("model fitted on wrong partition or split plan")
    contract = model.get("feature_contract")
    if type(contract) is not dict or (
        contract.get("names") != list(FEATURES) or
        contract.get("units") != list(FEATURE_UNITS) or
        contract.get("sample_rate_hz") != 1024 or
        contract.get("sample_count") != 1024
    ):
        raise ValueError("trained model feature/sample contract mismatch")
    centers, scales = model.get("center"), model.get("effective_scales")
    if type(centers) is not list or type(scales) is not list or len(centers) != len(FEATURES) or len(scales) != len(FEATURES):
        raise ValueError("wrong trained model parameter dimensions")
    if any(type(v) not in (int, float) or not isfinite(v) for v in centers) or any(
        type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in scales
    ):
        raise ValueError("nonfinite model means/scales")
    cal = model.get("calibration")
    if type(cal) is not dict or (
        cal.get("partition") != "train" or cal.get("comparison") != "score > threshold" or
        cal.get("quantile") != .99
    ):
        raise ValueError("threshold was not trained/calibrated on the training partition")
    threshold = cal.get("threshold")
    if type(threshold) not in (int, float) or not isfinite(threshold) or threshold < 0:
        raise ValueError("invalid trained anomaly threshold")
    cards = training.get("dataset_cards")
    expected = [sources[g] for g in sorted(training["groups"])]
    if type(cards) is not list or len(cards) != len(expected):
        raise ValueError("training dataset cards missing")
    for card, source in zip(cards, expected):
        if (type(card) is not dict or card.get("export_id") != source["source_id"]
                or card.get("model_source_sha256") != source["model_source_sha256"]
                or card.get("config_sha256") != source["config_sha256"]):
            raise ValueError("trained source/card provenance disagrees with split")
    verify_fitted_preprocessing(model.get("feature_processing"), model=model,
                                plan=plan, sources=sources)


def _regime(event: dict) -> str:
    cfg = event.get("operating_config")
    if type(cfg) is not dict:
        raise ValueError("operating_config must be an object")
    speed, load = cfg.get("speed_variation_pct"), cfg.get("load_variation_pct")
    if any(type(x) not in (int, float) or not isfinite(x) or not 0 <= x <= 1
           for x in (speed, load)):
        raise ValueError("invalid operating regime variation metadata")
    return "variable_speed_or_load" if speed > 0 or load > 0 else "nominal_speed_and_load"


def _truth(event: dict) -> tuple[bool, str]:
    scenario = event.get("scenario")
    if scenario not in (*FAULTS, "healthy"):
        raise ValueError("unknown effective synthetic fault truth")
    phase = event.get("fault_phase")
    # Effective event scenario, not the future configured fault label.
    # At the beginning of a zero-strength ramp, phase can be 'ramping'
    # while effective scenario remains 'healthy'. Do not label it a fault.
    if phase not in ("healthy", "scheduled", "ended", "ramping", "steady"):
        raise ValueError("unknown simulator fault phase")
    if scenario != "healthy" and phase not in ("ramping", "steady"):
        raise ValueError("synthetic effective fault label contradicts its phase")
    return scenario != "healthy", scenario


def _episodes(rows: list[dict], step_seconds: float) -> dict:
    """Compute first on-fault detection per continuous labeled episode.

    Sensor abstentions remain inside episodes; a fault is missed if no eligible
    window raises an alert. The first positive tick is the *observed* onset.
    """
    if not rows:
        return {"episodes": 0, "detected": 0, "missed": 0, "abstained_only": 0,
                "mean_delay_seconds": None, "median_delay_seconds": None, "details": []}
    ordered = sorted(rows, key=lambda r: (r["tick"], r["asset_id"]))
    episodes = []
    active = None
    for row in ordered:
        if row["positive"]:
            # contiguous positive truth windows within one asset timeline
            if active is None or row["tick"] != active["last_tick"] + 1 or row["scenario"] != active["fault_type"]:
                if active is not None:
                    episodes.append(active)
                active = {"fault_type": row["scenario"], "onset_tick": row["tick"],
                          "last_tick": row["tick"], "first_alert_tick": None,
                          "eligible_windows": 0, "abstentions": 0,
                          "first_timestamp_utc": row["timestamp_utc"]}
            else:
                active["last_tick"] = row["tick"]
            if row["eligible"]:
                active["eligible_windows"] += 1
                if row["anomaly_alert"] and active["first_alert_tick"] is None:
                    active["first_alert_tick"] = row["tick"]
            else:
                active["abstentions"] += 1
        elif active is not None:
            episodes.append(active)
            active = None
    if active is not None:
        episodes.append(active)
    details = []
    delays = []
    for e in episodes:
        first = e["first_alert_tick"]
        delay = (first - e["onset_tick"]) * step_seconds if first is not None else None
        if delay is not None:
            delays.append(delay)
        details.append({
            **e, "detected": first is not None, "delay_seconds": delay,
            "no_eligible_fault_windows": e["eligible_windows"] == 0,
            "onset_caveat": "first observed effective synthetic fault tick; not a real failure onset",
        })
    ordered_delays = sorted(delays)
    n = len(ordered_delays)
    return {
        "episodes": len(episodes),
        "detected": n, "missed": len(episodes) - n,
        "abstained_only": sum(e["eligible_windows"] == 0 for e in episodes),
        "mean_delay_seconds": sum(delays) / n if n else None,
        "median_delay_seconds": (
            (ordered_delays[(n-1)//2] + ordered_delays[n//2]) / 2 if n else None
        ),
        "details": details,
    }


def evaluate(plan: dict, manifests: Sequence[str | Path], model: dict, *,
             partition: str = "test", max_events: int = MAX_REPORT_EVENTS) -> dict:
    """Score a complete held-out partition; compare both methods on SAME good windows.

    Does not fit any model parameters. No test labels enter thresholding or
    feature choice. Unscorable windows are included in coverage, not confusion.
    """
    if partition not in EVAL_PARTITIONS:
        raise ValueError("evaluate validation or test only, never train")
    if type(max_events) is not int or not 0 <= max_events <= 100:
        raise ValueError("max_events must be an integer in [0, 100]")
    sources = _validated_sources(plan, manifests)
    _validate_model(model, plan, sources)
    group_ids = sorted(plan["partitions"][partition]["group_ids"])
    if plan["partitions"][partition]["records"] > MAX_EVALUATION_EVENTS:
        raise ValueError(f"evaluation exceeds {MAX_EVALUATION_EVENTS} synthetic windows")
    threshold = model["calibration"]["threshold"]
    centers, scales = model["center"], model["effective_scales"]
    eligible_rows: list[dict] = []
    by_track: dict[tuple[str, str], list[dict]] = defaultdict(list)
    abstentions = Counter()
    sample = []
    total = 0
    group_metadata = []
    for group_id in group_ids:
        source = sources[group_id]
        step = source["step_seconds"]
        if type(step) not in (float, int) or not isfinite(step) or step <= 0:
            raise ValueError("invalid synthetic virtual step")
        card = synthetic_run_card(source["path"].parent)
        if card["run_provenance"]["events_jsonl_sha256"] != source["source_data_sha256"]:
            raise ValueError("held-out dataset card and source checksum differ")
        group_metadata.append({
            "group_id": group_id, "source_id": source["source_id"],
            "dataset_card_id": card["card_id"],
            "source_data_sha256": source["source_data_sha256"],
            "model_source_sha256": source["model_source_sha256"],
            "config_sha256": source["config_sha256"],
            "step_seconds": step,
        })
        for event in _events(source):
            total += 1
            validate_window_contract(event)
            tick = event.get("tick")
            asset = event.get("asset_id")
            if type(tick) is not int or not 1 <= tick <= source["ticks"] or (
                type(asset) is not str or not asset
            ):
                raise ValueError("invalid source event tick/asset")
            positive, scenario = _truth(event)
            regime = _regime(event)
            quality = event.get("sensor_quality")
            health = event.get("health")
            if quality not in ("good", "missing", "outlier"):
                raise ValueError("invalid synthetic sensor-quality state")
            if quality == "good" and health not in ("normal", *RULE_ALERTS):
                raise ValueError("unexpected rule output for eligible measurement")
            if quality == "missing" and health != "unavailable":
                raise ValueError("missing sensor health must be unavailable")
            if quality == "outlier" and health != "suspect":
                raise ValueError("outlier sensor health must be suspect")
            row = {
                "group_id": group_id, "asset_id": asset,
                "tick": tick, "timestamp_utc": event.get("timestamp_utc"),
                "scenario": scenario, "positive": positive, "regime": regime,
                "eligible": quality == "good", "quality": quality,
                "rule_health": health, "step_seconds": step,
                "anomaly_alert": False, "rule_alert": False, "score": None,
            }
            if quality == "good":
                score = _score(_vector(event), centers, scales)
                if not isfinite(score):
                    raise ValueError("nonfinite synthetic anomaly score")
                row.update(score=score, anomaly_alert=score > threshold,
                           rule_alert=health in RULE_ALERTS)
                eligible_rows.append(row)
            else:
                abstentions[quality] += 1
            by_track[(group_id, asset)].append(row)
            if len(sample) < max_events:
                sample.append({
                    "group_id": group_id, "asset_id": asset, "tick": tick,
                    "timestamp_utc": row["timestamp_utc"],
                    "effective_synthetic_truth": scenario, "eligible": row["eligible"],
                    "sensor_quality": quality,
                    "anomaly_score": row["score"],
                    "model_decision": "anomaly" if row["anomaly_alert"] else (
                        "within_threshold" if row["eligible"] else "unscorable"),
                    "rule_based_health": health,
                })
    if total != plan["partitions"][partition]["records"]:
        raise ValueError("held-out records do not match split partition")
    if sum(len(x) for x in by_track.values()) != total:
        raise ValueError("held-out track membership mismatch")
    # Chronology and cardinality are important for episode duration/false alarms.
    for (group_id, asset), rows in by_track.items():
        source = sources[group_id]
        if len(rows) != source["ticks"] or [r["tick"] for r in rows] != list(range(1, source["ticks"] + 1)):
            raise ValueError(f"incomplete or disordered ticks in {group_id}/{asset}")
    def metric(rows, column):
        # Varying virtual steps require per-group negative exposure rather
        # than a single global step; provide simple counts regardless.
        result = confusion(rows, decision=column, with_ap=(column == "anomaly_alert"))
        neg_time = sum(r["step_seconds"] for r in rows if not r["positive"])
        result["false_alarms_per_simulated_negative_hour"] = (
            result["fp"] * 3600 / neg_time if neg_time > 0 else None
        )
        return result
    def compare(rows):
        return {"model": metric(rows, "anomaly_alert"), "rules": metric(rows, "rule_alert")}
    by_run = {
        g: compare([r for r in eligible_rows if r["group_id"] == g])
        for g in group_ids
    }
    by_motor = {
        f"{g}/{asset}": compare([r for r in eligible_rows if r["group_id"] == g and r["asset_id"] == asset])
        for g,asset in sorted(by_track)
    }
    by_regime = {
        key: compare([r for r in eligible_rows if r["regime"] == key])
        for key in sorted({r["regime"] for r in eligible_rows})
    }
    by_fault_type = {}
    for fault in FAULTS:
        positive_subset = [r for r in eligible_rows if r["scenario"] == fault]
        if positive_subset:
            by_fault_type[fault] = {
                "positive_windows": len(positive_subset),
                "model_detected": sum(r["anomaly_alert"] for r in positive_subset),
                "rule_detected": sum(r["rule_alert"] for r in positive_subset),
                "model_recall": sum(r["anomaly_alert"] for r in positive_subset)/len(positive_subset),
                "rule_recall": sum(r["rule_alert"] for r in positive_subset)/len(positive_subset),
                "note": "positive-only synthetic fault subset: precision, specificity and FPR not defined",
            }
    episodes = []
    for (group_id, asset), rows in sorted(by_track.items()):
        out = _episodes(rows, sources[group_id]["step_seconds"])
        for episode in out["details"]:
            episodes.append({"group_id": group_id, "asset_id": asset, **episode})
    delays = sorted(e["delay_seconds"] for e in episodes if e["delay_seconds"] is not None)
    n = len(delays)
    report = {
        "evaluation_version": "1.0.0", "source": "synthetic_only",
        "partition": partition, "whole_run_heldout": True,
        "trained_model_sha256": model["model_sha256"],
        "split_plan_sha256": plan["plan_sha256"],
        "training_groups": sorted(plan["partitions"]["train"]["group_ids"]),
        "evaluated_groups": group_ids, "source_provenance": group_metadata,
        "threshold_fixed_from_training": threshold,
        "feature_pipeline_sha256": model["feature_processing"]["pipeline_sha256"],
        "comparison_cohort": {
            "total_windows": total, "eligible_both_methods": len(eligible_rows),
            "abstentions": dict(sorted(abstentions.items())),
            "excluded_from_both_metrics": total-len(eligible_rows),
            "note": "only sensor_quality=good; missing/outlier windows excluded from BOTH model and rule denominators",
        },
        "overall": compare(eligible_rows),
        "by_run": by_run, "by_motor": by_motor, "by_operating_regime": by_regime,
        "by_fault_type_positive_only": by_fault_type,
        "detection_episodes": {
            "total": len(episodes), "detected": n, "missed": len(episodes)-n,
            "abstained_only": sum(e["eligible_windows"] == 0 for e in episodes),
            "mean_delay_seconds": sum(delays)/n if n else None,
            "median_delay_seconds": ((delays[(n-1)//2]+delays[n//2])/2) if n else None,
            "details": episodes,
        },
        "sample_events": sample,
        "metrics_note": "AP is non-interpolated average precision with tied scores grouped; undefined when only one class. FPR uses negatives as denominator. False alarms/hour counts negative eligible windows times virtual step as synthetic exposure, not field operating hours.",
        "label_note": "positive means effective scripted synthetic scenario != healthy, NOT scheduled future fault; model threshold/calibration frozen from training",
        "detection_note": "delay starts at first active synthetic fault tick; no claim of real fault lead time or RUL; episodes observed to partition boundary may be censored",
        "scientific_limit": "synthetic only; programmed truth and correlated generator runs are not independent physical validation, calibrated failure probabilities, or field maintenance advice",
    }
    report["evaluation_sha256"] = _hash(report)
    return report


def markdown(report: dict) -> str:
    """Small deterministic summary without full raw event duplication."""
    if report.get("evaluation_version") != "1.0.0":
        raise ValueError("unsupported evaluation report")
    cohort = report["comparison_cohort"]
    overall = report["overall"]
    lines = ["# MotorPulse AI — Held-out synthetic detection evaluation", "",
             f"**Partition:** {report['partition']} · **Model:** \`{report['trained_model_sha256']}\`",
             f"**Split:** \`{report['split_plan_sha256']}\`", "",
             f"**Eligible windows:** {cohort['eligible_both_methods']} / {cohort['total_windows']}; "
             f"abstentions: {cohort['abstentions']}", "",
             "| Metric | Trained model | Existing rules |",
             "| --- | ---: | ---: |"]
    for label, key in (("TP","tp"),("FP","fp"),("TN","tn"),("FN","fn"),
                       ("Precision","precision"),("Recall","recall"),
                       ("F1","f1"),("FPR","false_positive_rate"),
                       ("False alarms / simulated negative hour","false_alarms_per_simulated_negative_hour"),
                       ("Average precision (PR)","average_precision")):
        vals = []
        for method in ("model","rules"):
            x = overall[method][key]
            vals.append("undefined" if x is None else str(round(x, 6)) if isinstance(x, float) else str(x))
        lines.append(f"| {label} | {vals[0]} | {vals[1]} |")
    episodes = report["detection_episodes"]
    lines += ["", f"**Synthetic fault episodes:** {episodes['total']}, "
              f"model detected {episodes['detected']}, missed {episodes['missed']}; "
              f"mean model delay {episodes['mean_delay_seconds']} simulated seconds.",
              "", "> Both systems are compared on exactly the same good-sensor windows.",
              "", "> No field diagnosis, failure probability, physical lead time, RUL or industrial safety claim.",
              "", "All metrics are synthetic-only. Undefined denominators appear as undefined/null. "
              "Rule outputs are uncalibrated, and the fixed model threshold comes from training only.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen healthy-trained MP-010 scores versus heuristic rules on disjoint synthetic runs")
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True,
                        help="MP-010 trained JSON or MP-035 verified portable artifact")
    parser.add_argument("--input", nargs="+", type=Path, required=True,
                        help="ALL source manifest.json files listed in MP-030 plan")
    parser.add_argument("--partition", choices=EVAL_PARTITIONS, default="test")
    parser.add_argument("--out", type=Path, required=True, help="new JSON report; never overwritten")
    parser.add_argument("--markdown", type=Path, help="optional new Markdown summary")
    args = parser.parse_args()
    try:
        plan = _read_strict_json(args.split, 256 * 1024)
        package = _read_strict_json(args.model, 512 * 1024)
        if type(package) is not dict:
            raise ValueError("--model must be a JSON object")
        if "artifact_version" in package:
            # Full MP-035 source/card/model verification before any scoring.
            from .model_artifact import verify_model_artifact
            trained = verify_model_artifact(package, plan, args.input)
        elif type(package.get("model")) is dict:
            # Backward compatible MP-010 wrapper; evaluate() still validates
            # split, source-group, model and MP-034 preprocessing provenance.
            trained = package["model"]
        else:
            raise ValueError("--model must be MP-010 JSON or MP-035 artifact")
        result = evaluate(plan, args.input, trained, partition=args.partition)
        if args.markdown and args.markdown.resolve() == args.out.resolve():
            raise ValueError("JSON and Markdown outputs must have different paths")
        # Preflight both output paths so we never clobber existing artifacts.
        for dest in (args.out, args.markdown):
            if dest is not None and (not dest.parent.is_dir() or dest.exists()):
                raise ValueError(f"output parent missing or output already exists: {dest}")
        write_local_manifest(args.out, result)
        if args.markdown:
            try:
                with args.markdown.open("x", encoding="utf-8", newline="\n") as fp:
                    fp.write(markdown(result))
            except BaseException:
                args.out.unlink(missing_ok=True)
                raise
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Evaluated {result['comparison_cohort']['eligible_both_methods']} eligible "
          f"synthetic held-out windows; report={args.out}, partition={args.partition}")


if __name__ == "__main__":
    main()
