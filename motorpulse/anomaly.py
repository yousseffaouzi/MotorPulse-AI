"""MP-010: transparent healthy-trained synthetic anomaly baseline.

Uses validated MP-030 whole-run plans and MP-032 dataset cards. Fits only
healthy, sensor-good training events. Never fits from evaluation partitions.
This is a *synthetic anomaly score*, not a physical failure probability.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from math import isfinite, sqrt
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

from .dataset_cards import synthetic_run_card
from .eda import MAX_LINE_BYTES, MAX_SYNTHETIC_EVENTS, _json
from .ims import _read_strict_json, write_local_manifest
from .splits import _hash, _source, PARTITIONS

FEATURES = ("rms_g", "crest_factor", "band_80_400_rms_g",
            "temperature_c", "rpm")
FEATURE_UNITS = ("g RMS", "dimensionless", "g RMS", "degC", "rpm")
MIN_HEALTHY_SAMPLES = 8
MAX_GROUPS = 100
MODEL_VERSION = "1.0.0"
TRAIN_QUANTILE = 0.99


def _percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("empty score distribution")
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _validated_sources(plan: dict, manifests: Sequence[str | Path]) -> dict[str, dict]:
    """Reject forged/stale plans, missing runs, ambiguous group identity.

    Every source is separately rechecked via MP-029's integrity validation.
    All groups in the original whole-run plan must be supplied, not just train.
    """
    if not isinstance(plan, dict) or plan.get("split_version") != "1.0.0" or (
        plan.get("policy") != "whole_run_grouped" or
        plan.get("source_type") != "synthetic_motor_feature_events" or
        plan.get("publication_status") != "synthetic_demo" or
        plan.get("label_blind_assignment") is not True
    ):
        raise ValueError("healthy anomaly training requires an MP-030 whole-run synthetic split")
    checksum = plan.get("plan_sha256")
    if type(checksum) is not str or _hash({k: v for k, v in plan.items()
                                         if k != "plan_sha256"}) != checksum:
        raise ValueError("split plan checksum mismatch")
    if not isinstance(manifests, (list, tuple)) or not 3 <= len(manifests) <= MAX_GROUPS:
        raise ValueError("supply every planned source manifest (3-100)")
    sources = [_source(path, "synthetic") for path in manifests]
    expected = plan.get("sources")
    if (not isinstance(expected, list) or
            sorted(sources, key=lambda entry: entry["group_id"]) != expected):
        raise ValueError("supplied source identity, digest or configuration differs from split plan")
    by_group = {s["group_id"]: {**s, "path": Path(p)} for s, p in zip(sources, manifests)}
    if len(by_group) != len(sources):
        raise ValueError("duplicate source groups")
    parts = plan.get("partitions")
    if type(parts) is not dict or set(parts) != set(PARTITIONS):
        raise ValueError("plan partitions missing or unexpected")
    all_groups = set()
    for partition in PARTITIONS:
        entry = parts[partition]
        ids = entry.get("group_ids")
        if type(ids) is not list or not ids or len(ids) != len(set(ids)):
            raise ValueError("partition needs unique nonempty group IDs")
        if any(group_id not in by_group or group_id in all_groups for group_id in ids):
            raise ValueError("overlapping or missing source group")
        all_groups.update(ids)
        if (entry.get("groups") != len(ids) or
                sorted(by_group[g]["source_id"] for g in ids) != entry.get("source_ids") or
                sum(by_group[g]["records"] for g in ids) != entry.get("records")):
            raise ValueError("partition counts or source IDs disagree with manifests")
    if all_groups != set(by_group):
        raise ValueError("split plan omitted source groups")
    return by_group


def _events(source: dict):
    """Read only a bounded, already-verified JSONL, with a second digest check."""
    folder = source["path"].parent
    p = folder / "events.jsonl"
    if p.is_symlink() or not p.is_file():
        raise ValueError("synthetic events JSONL is missing or symlinked")
    digest = hashlib.sha256()
    count = 0
    with p.open("rb") as stream:
        while True:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LINE_BYTES:
                raise ValueError("overlong synthetic event line")
            digest.update(line)
            count += 1
            if count > MAX_SYNTHETIC_EVENTS:
                raise ValueError("synthetic event count exceeds limit")
            try:
                event = _json(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"corrupt synthetic JSONL event {count}") from exc
            if (type(event) is not dict or event.get("export_id") != source["source_id"]
                    or event.get("source") != "synthetic"):
                raise ValueError("event source provenance mismatch")
            yield event
    if count != source["records"] or digest.hexdigest() != source["source_data_sha256"]:
        raise ValueError("event count or JSONL SHA-256 changed after validation")


def _vector(event: dict) -> tuple[float, ...]:
    """Strict feature allowlist; NO fault truth, rules, asset ID or timestamps."""
    result = []
    for name in FEATURES:
        x = event.get(name)
        if type(x) not in (int, float) or not isfinite(x):
            raise ValueError(f"unscorable feature {name}; expected finite number")
        result.append(float(x))
    if any(x < 0 for x in result):
        raise ValueError("negative vibration/crest/temp/RPM value outside this demo contract")
    return tuple(result)


def _score(values: tuple[float, ...], centers: list[float], scales: list[float]) -> float:
    return sqrt(sum(((v - mu) / scale) ** 2
                    for v, mu, scale in zip(values, centers, scales)) / len(FEATURES))


def train_baseline(plan: dict, manifests: Sequence[str | Path]) -> dict:
    """Fit on *training-partition* synthetic healthy + good-sensor windows only.

    Uses only training feature values to estimate means, population deviations,
    scale floors and a 99th-percentile training score threshold.
    """
    sources = _validated_sources(plan, manifests)
    healthy = []
    rejection = Counter()
    train_groups = plan["partitions"]["train"]["group_ids"]
    train_cards = []
    for group_id in sorted(train_groups):
        source = sources[group_id]
        card = synthetic_run_card(source["path"].parent)
        if card["run_provenance"]["events_jsonl_sha256"] != source["source_data_sha256"]:
            raise ValueError("dataset card / split source checksum mismatch")
        train_cards.append({"card_id": card["card_id"],
                            "export_id": source["source_id"],
                            "config_sha256": source["config_sha256"],
                            "model_source_sha256": source["model_source_sha256"]})
        for event in _events(source):
            if event.get("sensor_quality") != "good":
                rejection["bad_sensor_quality"] += 1
                continue
            if event.get("scenario") != "healthy":
                rejection["nonhealthy_synthetic_truth"] += 1
                continue
            healthy.append(_vector(event))
    if len(healthy) < MIN_HEALTHY_SAMPLES:
        raise ValueError(f"need at least {MIN_HEALTHY_SAMPLES} healthy good-sensor training events")
    centers = [fmean(row[j] for row in healthy) for j in range(len(FEATURES))]
    deviations = [sqrt(fmean((row[j] - centers[j]) ** 2 for row in healthy))
                  for j in range(len(FEATURES))]
    # An exact/near-constant training feature should not divide by zero.
    # This engineering floor prevents numerical explosions; not calibration.
    scales = [max(sd, abs(mu) * 0.01, 1e-6)
              for mu, sd in zip(centers, deviations)]
    distances = [_score(v, centers, scales) for v in healthy]
    threshold = _percentile(distances, TRAIN_QUANTILE)
    if not all(isfinite(x) for x in centers + deviations + scales + distances + [threshold]):
        raise ValueError("nonfinite training statistics")
    model = {
        "model_version": MODEL_VERSION,
        "method": "healthy_training_zscore_euclidean",
        "score_direction": "higher_is_more_unusual",
        "score_is_failure_probability": False,
        "remaining_useful_life": None,
        "feature_contract": {
            "names": list(FEATURES), "units": list(FEATURE_UNITS),
            "source": "MotorPulse synthetic feature events only",
            "sample_rate_hz": 1024, "sample_count": 1024,
            "excluded_inputs": ["scenario", "severity", "configured_scenario",
                                "health", "reasons", "fault_phase", "sensor_quality",
                                "asset_id", "timestamp_utc", "export_id"],
            "missing_policy": "reject or mark unscorable; no zero-filling",
            "outlier_policy": "sensor_quality=outlier is unscorable",
        },
        "training": {
            "split_plan_sha256": plan["plan_sha256"],
            "groups": sorted(train_groups),
            "healthy_good_sensor_events": len(healthy),
            "excluded_training_events": dict(sorted(rejection.items())),
            "dataset_cards": train_cards,
            "fit_partitions": ["train"],
        },
        "calibration": {
            "partition": "train",
            "quantile": TRAIN_QUANTILE,
            "threshold": threshold,
            "comparison": "score > threshold",
            "training_score_max": max(distances),
            "method_note": "in-sample empirical quantile; not a guaranteed false-alarm rate",
        },
        "center": centers, "population_std": deviations, "effective_scales": scales,
        "limitations": [
            "Synthetic-only healthy-trained anomaly score; not a calibrated failure probability or RUL",
            "Training-only 99th percentile is in-sample and not a statistically validated false-alarm guarantee",
            "Correlated synthetic generators and changed loads/speeds can increase scores without machine faults",
            "Missing/outlier sensor events have no anomaly score; calibration has not been validated on real sensors",
        ],
        "publication_status": "synthetic_demo",
    }
    model["model_sha256"] = _hash(model)
    return model


def score_partition(plan: dict, manifests: Sequence[str | Path], model: dict,
                    *, partition: str, max_events: int = 30) -> dict:
    """Score only declared whole-run partitions, without updating trained state."""
    if partition not in PARTITIONS:
        raise ValueError("partition must be train, validation or test")
    if type(max_events) is not int or not 1 <= max_events <= 12000:
        raise ValueError("max_events must be between 1 and 12000")
    sources = _validated_sources(plan, manifests)
    if (not isinstance(model, dict) or
            model.get("model_version") != MODEL_VERSION or
            model.get("training", {}).get("split_plan_sha256") != plan["plan_sha256"] or
            model.get("training", {}).get("groups") != sorted(plan["partitions"]["train"]["group_ids"]) or
            _hash({k: v for k, v in model.items() if k != "model_sha256"}) != model.get("model_sha256")):
        raise ValueError("model provenance or checksum mismatch")
    centers = model["center"]
    scales = model["effective_scales"]
    if (model.get("feature_contract", {}).get("names") != list(FEATURES) or
            len(centers) != len(FEATURES) or len(scales) != len(FEATURES) or
            any(type(x) not in (float, int) or not isfinite(x) for x in centers) or
            any(type(x) not in (float, int) or not isfinite(x) or x <= 0 for x in scales)):
        raise ValueError("invalid trained model feature contract")
    threshold = model.get("calibration", {}).get("threshold")
    if type(threshold) not in (float, int) or not isfinite(threshold) or threshold < 0:
        raise ValueError("invalid model threshold")
    outputs = []
    seen = 0
    classes = Counter()
    rejected = Counter()
    for group_id in sorted(plan["partitions"][partition]["group_ids"]):
        for event in _events(sources[group_id]):
            seen += 1
            quality = event.get("sensor_quality")
            if quality != "good":
                reason = "missing_sensor" if quality == "missing" else "sensor_outlier"
                rejected[reason] += 1
                status = "unscorable"
                value = None
            else:
                value = _score(_vector(event), centers, scales)
                if not isfinite(value):
                    raise ValueError("nonfinite scored event")
                status = "anomaly" if value > threshold else "within_training_threshold"
                classes[status] += 1
            if len(outputs) < max_events:
                outputs.append({
                    "group_id": group_id,
                    "asset_id": event["asset_id"], "tick": event["tick"],
                    "event_id": event["event_id"], "timestamp_utc": event["timestamp_utc"],
                    "sensor_quality": quality,
                    "anomaly_score": value, "decision": status,
                    "rule_based_health": event["health"],
                    "note": "rule health is separate; anomaly score is not failure probability",
                })
    return {
        "score_report_version": "1.0.0", "partition": partition,
        "model_sha256": model["model_sha256"],
        "split_plan_sha256": plan["plan_sha256"],
        "total_events": seen, "displayed_events": len(outputs),
        "counts_by_decision": dict(sorted(classes.items())),
        "counts_unscorable": dict(sorted(rejected.items())),
        "events_sample": outputs,
        "sampling_note": "first N events by sorted run group and event order, not a benchmark",
        "evaluation_note": "no held-out metrics or failure probability; MP-011 follows",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a healthy-only synthetic anomaly baseline using a whole-run MP-030 split")
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--input", type=Path, nargs="+", required=True,
                        help="ALL synthetic manifest.json paths used to create the split")
    parser.add_argument("--out", type=Path, required=True,
                        help="NEW local model JSON; no overwrite")
    parser.add_argument("--preview", choices=PARTITIONS, default="validation",
                        help="partition for informational scoring preview")
    args = parser.parse_args()
    try:
        plan = _read_strict_json(args.split, 256 * 1024)
        model = train_baseline(plan, args.input)
        preview = score_partition(plan, args.input, model, partition=args.preview)
        write_local_manifest(args.out, {"model": model, "preview": preview})
    except (ValueError, OSError, TypeError, KeyError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Trained synthetic-only baseline: {args.out}; "
          f"healthy train events={model['training']['healthy_good_sensor_events']}; "
          f"train threshold={model['calibration']['threshold']:.4g}")


if __name__ == "__main__":
    main()
