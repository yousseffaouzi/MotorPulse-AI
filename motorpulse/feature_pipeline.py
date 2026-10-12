"""MP-034: train-only feature preprocessing and explicit window-leakage guards.

All features come from synthetic MotorPulse schema only. Training truth is used
solely as an eligibility gate, never as a numeric model feature.
"""
from __future__ import annotations

import hashlib
import json
from math import ceil, isfinite, sqrt
from statistics import fmean
from typing import Any, Sequence

VERSION = "1.0.0"
FEATURES = ("rms_g", "crest_factor", "band_80_400_rms_g", "temperature_c", "rpm")
UNITS = ("g RMS", "dimensionless", "g RMS", "degC", "rpm")
EXCLUDED = ("scenario", "severity", "configured_scenario", "configured_severity",
            "fault_phase", "ramp_fraction", "health", "reasons",
            "sensor_quality", "sensor_quality_reasons", "asset_id", "name",
            "event_id", "export_id", "source", "tick", "timestamp_utc",
            "recorded_at_utc", "operating_config", "load_factor")
SAMPLE_RATE_HZ = 1024
SAMPLE_COUNT = 1024
ROLLING_TICKS = 5
MIN_SAMPLES = 8


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def numeric_features(event: dict) -> tuple[float, ...]:
    """Whitelisted numeric vector; no fault labels, rule results, run identity."""
    if type(event) is not dict:
        raise ValueError("feature event must be an object")
    values = []
    for key in FEATURES:
        item = event.get(key)
        if type(item) not in (int, float) or not isfinite(item) or item < 0:
            raise ValueError(f"invalid or missing numeric feature {key}")
        values.append(float(item))
    return tuple(values)


def validate_window_contract(event: dict) -> None:
    """Protect this baseline from silently ingesting other sampling schemes.

    The rolling history is computed *within each simulator run*; whole-run
    train/test isolation prevents that history from straddling partitions.
    """
    if type(event) is not dict:
        raise ValueError("event must be an object")
    for key, expected in (("sample_rate_hz", SAMPLE_RATE_HZ),
                          ("sample_count", SAMPLE_COUNT),
                          ("rolling_window_ticks", ROLLING_TICKS)):
        if type(event.get(key)) is not int or event[key] != expected:
            raise ValueError(f"unexpected synthetic window contract: {key}")
    duration = event.get("window_duration_s")
    if type(duration) not in (int, float) or not isfinite(duration) or abs(duration - 1.0) > 1e-9:
        raise ValueError("unsupported synthetic waveform window duration")
    tick = event.get("tick")
    observations = event.get("rolling_observations")
    valid = event.get("rolling_valid_observations")
    if (type(tick) is not int or tick < 1 or
            type(observations) is not int or not 1 <= observations <= min(tick, ROLLING_TICKS) or
            type(valid) is not int or not 0 <= valid <= observations):
        raise ValueError("invalid rolling feature history/counts")
    if type(event.get("asset_id")) is not str or not event["asset_id"]:
        raise ValueError("missing source motor identity")


def _strict_numbers(values: Any, *, positive: bool = False) -> bool:
    return (type(values) is list and len(values) == len(FEATURES) and
            all(type(x) in (float, int) and isfinite(x) and
                (not positive or x > 0) for x in values))


def fit_preprocessing(rows: Sequence[tuple[str, dict]], *,
                      train_groups: Sequence[str], split_plan_sha256: str,
                      source_hashes: dict[str, str]) -> dict:
    """Fit scaling exclusively on authorized training groups.

    Each row must be a healthy, sensor-good training event. Duplicate
    (run, asset, tick) windows are forbidden. No imputer, clipping, feature
    selection, or learned transformation is applied to held-out data.
    """
    if (type(split_plan_sha256) is not str or len(split_plan_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in split_plan_sha256)):
        raise ValueError("invalid split-plan SHA-256")
    if (not isinstance(train_groups, (list, tuple)) or not train_groups or
            any(type(g) is not str or not g for g in train_groups) or
            len(set(train_groups)) != len(train_groups) or
            type(source_hashes) is not dict or set(source_hashes) != set(train_groups) or
            any(type(v) is not str or len(v) != 64 or
                any(c not in "0123456789abcdef" for c in v) for v in source_hashes.values())):
        raise ValueError("invalid training-only group/source provenance")
    if not isinstance(rows, (list, tuple)):
        raise ValueError("training rows must be explicitly supplied")
    seen = set()
    vectors = []
    for group, event in rows:
        if group not in train_groups:
            raise ValueError("feature preprocessing cannot fit on held-out groups")
        validate_window_contract(event)
        if event.get("scenario") != "healthy" or event.get("sensor_quality") != "good":
            raise ValueError("preprocessing fit requires healthy good-sensor training truth")
        key = (group, event["asset_id"], event["tick"])
        if key in seen:
            raise ValueError("repeated training window identity")
        seen.add(key)
        vectors.append(numeric_features(event))
    if len(vectors) < MIN_SAMPLES:
        raise ValueError(f"need at least {MIN_SAMPLES} healthy good-sensor training events")
    center = [fmean(row[j] for row in vectors) for j in range(len(FEATURES))]
    population_std = [
        sqrt(fmean((row[j] - center[j]) ** 2 for row in vectors))
        for j in range(len(FEATURES))
    ]
    scales = [max(sd, abs(mu) * .01, 1e-6) for mu, sd in zip(center, population_std)]
    if not _strict_numbers(center) or not _strict_numbers(population_std) or not _strict_numbers(scales, positive=True):
        raise ValueError("nonfinite fitted preprocessing parameters")
    pipeline = {
        "pipeline_version": VERSION, "fit_partition": "train",
        "train_groups": sorted(train_groups),
        "train_source_sha256": dict(sorted(source_hashes.items())),
        "split_plan_sha256": split_plan_sha256,
        "feature_names": list(FEATURES), "feature_units": list(UNITS),
        "excluded_inputs": list(EXCLUDED),
        "sampling": {"sample_rate_hz": SAMPLE_RATE_HZ, "sample_count": SAMPLE_COUNT,
                     "waveform_window_seconds": 1.0,
                     "rolling_lookback_ticks": ROLLING_TICKS},
        "training_windows": len(vectors),
        "selection": "scenario=healthy and sensor_quality=good in train runs only",
        "missing_policy": "reject/unscorable; never impute from validation/test",
        "outlier_policy": "unscorable; never fit on injected sensor outliers",
        "feature_selection": "fixed allowlist; not learned from held-out labels",
        "normalization": "training population mean/std with 1 percent mean and 1e-6 scale floors",
        "center": center, "population_std": population_std, "effective_scales": scales,
    }
    pipeline["pipeline_sha256"] = _hash(pipeline)
    return pipeline


def verify_fitted_preprocessing(pipeline: Any, *,
                                model: dict, plan: dict, sources: dict) -> None:
    """Reject stale/tampered or re-fitted parameter records before scoring."""
    if type(pipeline) is not dict or pipeline.get("pipeline_version") != VERSION or (
        pipeline.get("fit_partition") != "train" or
        pipeline.get("split_plan_sha256") != plan.get("plan_sha256") or
        pipeline.get("train_groups") != sorted(plan["partitions"]["train"]["group_ids"]) or
        pipeline.get("feature_names") != list(FEATURES) or
        pipeline.get("feature_units") != list(UNITS) or
        pipeline.get("excluded_inputs") != list(EXCLUDED)
    ):
        raise ValueError("preprocessing feature/split contract mismatch")
    if (pipeline.get("sampling") != {"sample_rate_hz": SAMPLE_RATE_HZ,
                                    "sample_count": SAMPLE_COUNT,
                                    "waveform_window_seconds": 1.0,
                                    "rolling_lookback_ticks": ROLLING_TICKS} or
            pipeline.get("train_source_sha256") !=
            {g: sources[g]["source_data_sha256"] for g in sorted(plan["partitions"]["train"]["group_ids"])}):
        raise ValueError("preprocessing training source/sampling mismatch")
    if (not _strict_numbers(pipeline.get("center")) or
            not _strict_numbers(pipeline.get("population_std")) or
            not _strict_numbers(pipeline.get("effective_scales"), positive=True) or
            pipeline["center"] != model.get("center") or
            pipeline["population_std"] != model.get("population_std") or
            pipeline["effective_scales"] != model.get("effective_scales")):
        raise ValueError("model/preprocessing fitted parameters differ")
    if (type(pipeline.get("training_windows")) is not int or
            pipeline["training_windows"] < MIN_SAMPLES or
            pipeline["training_windows"] != model.get("training", {}).get("healthy_good_sensor_events")):
        raise ValueError("preprocessing window count does not match model training")
    if (type(pipeline.get("pipeline_sha256")) is not str or
            _hash({k: v for k, v in pipeline.items() if k != "pipeline_sha256"}) != pipeline["pipeline_sha256"]):
        raise ValueError("preprocessing checksum mismatch")


def validate_chronological_boundaries(plan: dict, *,
                                      window_duration_s: float,
                                      step_seconds: float,
                                      rolling_ticks: int = ROLLING_TICKS) -> int:
    """Check *exploratory* same-run partitions for lookback + waveform gaps.

    This never authorizes MP-010 model training on within-run partitions.
    Model training still exclusively requires whole-run MP-030 plans.
    """
    if type(plan) is not dict or plan.get("policy") != "synthetic_chronological_exploratory":
        raise ValueError("not an exploratory synthetic chronological split")
    if (type(rolling_ticks) is not int or rolling_ticks < 1 or
            type(window_duration_s) not in (int, float) or
            type(step_seconds) not in (int, float) or
            not isfinite(window_duration_s) or not isfinite(step_seconds) or
            window_duration_s <= 0 or step_seconds <= 0):
        raise ValueError("invalid waveform/rolling-window geometry")
    required = max(rolling_ticks - 1, ceil(window_duration_s / step_seconds))
    ranges = plan.get("partitions")
    if type(ranges) is not dict or set(ranges) != {"train", "validation", "test"}:
        raise ValueError("invalid temporal partition plan")
    previous_end = None
    expected_purges = []
    for name in ("train", "validation", "test"):
        entry = ranges[name]
        if not isinstance(entry, dict):
            raise ValueError("invalid temporal range")
        start, end = entry.get("tick_start"), entry.get("tick_end")
        if type(start) is not int or type(end) is not int or start < 1 or end < start:
            raise ValueError("invalid temporal tick boundaries")
        if type(entry.get("ticks")) is not int or entry["ticks"] != end - start + 1:
            raise ValueError("nonconsecutive or incomplete temporal range")
        if previous_end is None:
            if start != 1:
                raise ValueError("first temporal range must start at tick 1")
        else:
            gap = start - previous_end - 1
            if gap < required:
                raise ValueError(f"temporal data leakage: need at least {required} purged ticks")
            expected_purges.append({"tick_start": previous_end + 1, "tick_end": start - 1})
        previous_end = end
    if plan.get("purged_ranges") != expected_purges:
        raise ValueError("purge metadata differs from actual temporal boundaries")
    if type(plan.get("purge_ticks")) is not int or plan["purge_ticks"] < required:
        raise ValueError("reported purge_ticks insufficient for source geometry")
    if type(plan.get("minimum_purge_ticks")) is not int or plan["minimum_purge_ticks"] != required:
        raise ValueError("reported minimum purge disagrees with source geometry")
    return required
