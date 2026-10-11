"""Versioned JSON telemetry contract and dependency-free runtime validation.

The schema describes emitted *feature summaries*, not raw waveform samples.
See docs/TELEMETRY.md for versioning and time/units conventions.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

SCHEMA_VERSION = "1.0.0"
SAMPLE_RATE_HZ = 1024
SAMPLE_COUNT = 1024
SENSOR_UNITS = {
    "vibration_acceleration": "g",  # acceleration in standard gravity units
    "temperature": "degC",
    "rotational_speed": "rpm",
}
HEALTH_STATES = frozenset({"normal", "warning", "critical", "unavailable", "suspect"})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Invalid telemetry: {message}")


def _utc_timestamp(value: Any, field: str) -> None:
    _require(isinstance(value, str), f"{field} must be a UTC ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid telemetry: {field} must be ISO 8601") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0),
             f"{field} must have UTC offset (+00:00 or Z)")


def _numeric(value: Any, field: str, *, min_value: float | None = None) -> None:
    _require(type(value) in (int, float) and isfinite(value),
             f"{field} must be a finite number")
    if min_value is not None:
        _require(value >= min_value, f"{field} must be >= {min_value}")


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    """Raise ValueError for a malformed v1 snapshot; accept added optional fields.

    This lightweight validator is deliberately standard-library-only. A JSON
    Schema 2020-12 definition is also published for external consumers.
    """
    _require(isinstance(snapshot, Mapping), "snapshot must be an object")
    _require(snapshot.get("schema_version") == SCHEMA_VERSION,
             f"schema_version must be {SCHEMA_VERSION}")
    _require(isinstance(snapshot.get("source"), str) and bool(snapshot["source"]),
             "source must be nonempty text")
    _require(type(snapshot.get("tick")) is int and snapshot["tick"] >= 1,
             "tick must be a positive integer")
    _utc_timestamp(snapshot.get("recorded_at_utc"), "recorded_at_utc")
    assets = snapshot.get("assets")
    _require(isinstance(assets, list), "assets must be a list")
    event_ids: set[str] = set()
    asset_ids: set[str] = set()
    for index, event in enumerate(assets):
        prefix = f"assets[{index}]"
        _require(isinstance(event, Mapping), f"{prefix} must be an object")
        for key in ("event_id", "asset_id", "name", "scenario", "source"):
            _require(isinstance(event.get(key), str) and bool(event[key]),
                     f"{prefix}.{key} must be nonempty text")
        _require(event["source"] == snapshot["source"],
                 f"{prefix}.source must match source")
        _require(event["event_id"] not in event_ids,
                 f"duplicate event_id {event['event_id']}")
        _require(event["asset_id"] not in asset_ids,
                 f"duplicate asset_id {event['asset_id']}")
        event_ids.add(event["event_id"])
        asset_ids.add(event["asset_id"])
        _utc_timestamp(event.get("timestamp_utc"), f"{prefix}.timestamp_utc")
        _require(event["timestamp_utc"] == snapshot["recorded_at_utc"],
                 f"{prefix}.timestamp_utc must match snapshot time in v1")
        _require(event.get("units") == SENSOR_UNITS,
                 f"{prefix}.units must declare the canonical sensor units")
        for key in ("sample_rate_hz", "sample_count"):
            _require(type(event.get(key)) is int and event[key] > 0,
                     f"{prefix}.{key} must be a positive integer")
        # New optional v1 fields preserve compatibility with old fixture data.
        if "window_duration_s" in event:
            _numeric(event["window_duration_s"], f"{prefix}.window_duration_s", min_value=0)
            _require(abs(event["window_duration_s"] -
                         event["sample_count"] / event["sample_rate_hz"]) <= 1e-9,
                     f"{prefix}.window_duration_s must match sample_count / sample_rate_hz")
        quality = event.get("sensor_quality", "good")
        _require(type(quality) is str and quality in ("good", "missing", "outlier"),
                 f"{prefix}.sensor_quality invalid")
        if "sensor_quality_reasons" in event:
            qr = event["sensor_quality_reasons"]
            _require(isinstance(qr, list) and
                     all(isinstance(reason, str) and bool(reason) for reason in qr),
                     f"{prefix}.sensor_quality_reasons must be a list of nonempty strings")
        if "load_factor" in event:
            _numeric(event["load_factor"], f"{prefix}.load_factor", min_value=0)
        if "sensor_drift_g" in event:
            _numeric(event["sensor_drift_g"], f"{prefix}.sensor_drift_g")
            _require(abs(event["sensor_drift_g"]) <= 0.5,
                     f"{prefix}.sensor_drift_g out of bounds")
        if "operating_config" in event:
            conf = event["operating_config"]
            _require(isinstance(conf, Mapping), f"{prefix}.operating_config must be an object")
            for key, lo, hi in (("speed_variation_pct", 0, .2),
                                ("load_variation_pct", 0, .3),
                                ("sensor_noise_g", 0, .1),
                                ("sensor_drift_g_per_tick", -.001, .001)):
                _numeric(conf.get(key), f"{prefix}.operating_config.{key}")
                _require(lo <= conf[key] <= hi, f"{prefix}.operating_config.{key} out of bounds")
        for key in ("rpm", "rms_g", "peak_to_peak_g", "crest_factor"):
            value = event.get(key)
            if quality == "missing" and key != "rpm" and value is None:
                continue
            _numeric(value, f"{prefix}.{key}", min_value=0)
        if "shaft_frequency_hz" in event:
            _numeric(event["shaft_frequency_hz"], f"{prefix}.shaft_frequency_hz", min_value=0)
            _require(abs(event["shaft_frequency_hz"] - event["rpm"] / 60) <= 0.001,
                     f"{prefix}.shaft_frequency_hz must correspond to rpm / 60")
        # Optional additive MP-007 fields preserve compatibility with older clients.
        if "severity" in event:
            _numeric(event["severity"], f"{prefix}.severity", min_value=0)
            _require(event["severity"] <= 1, f"{prefix}.severity must be <= 1")
        if "configured_severity" in event:
            _numeric(event["configured_severity"], f"{prefix}.configured_severity", min_value=0)
            _require(event["configured_severity"] <= 1, f"{prefix}.configured_severity must be <= 1")
        if "configured_scenario" in event:
            from .scenarios import SCENARIOS
            _require(event["configured_scenario"] in SCENARIOS,
                     f"{prefix}.configured_scenario invalid")
        if "onset_tick" in event:
            _require(type(event["onset_tick"]) is int and 1 <= event["onset_tick"] <= 100000,
                     f"{prefix}.onset_tick invalid")
        if "duration_ticks" in event:
            d = event["duration_ticks"]
            _require(d is None or (type(d) is int and 1 <= d <= 100000),
                     f"{prefix}.duration_ticks invalid")
        # MP-020 adds optional severity-ramp fields to the v1 event.
        if "progression" in event:
            from .scenarios import PROGRESSION_PROFILES
            _require(isinstance(event["progression"], str) and
                     event["progression"] in PROGRESSION_PROFILES,
                     f"{prefix}.progression invalid")
        if "start_severity" in event:
            _numeric(event["start_severity"], f"{prefix}.start_severity", min_value=0)
            _require(event["start_severity"] <= 1, f"{prefix}.start_severity must be <= 1")
        if "ramp_ticks" in event:
            rt = event["ramp_ticks"]
            _require(rt is None or (type(rt) is int and 2 <= rt <= 100000),
                     f"{prefix}.ramp_ticks invalid")
        if "ramp_fraction" in event:
            _numeric(event["ramp_fraction"], f"{prefix}.ramp_fraction", min_value=0)
            _require(event["ramp_fraction"] <= 1, f"{prefix}.ramp_fraction must be <= 1")
        if "fault_phase" in event:
            _require(isinstance(event["fault_phase"], str) and
                     event["fault_phase"] in ("healthy", "scheduled", "ramping", "steady", "ended"),
                     f"{prefix}.fault_phase invalid")
        # MP-023 optional FFT and tick-based rolling summaries.
        if "spectral_window" in event:
            _require(event["spectral_window"] == "hann", f"{prefix}.spectral_window must be hann")
        for key in ("spectral_bin_hz", "dominant_frequency_hz",
                    "shaft_1x_amplitude_g", "shaft_2x_amplitude_g",
                    "band_80_400_rms_g", "rolling_rms_mean_g"):
            if key in event:
                if quality == "missing" and event[key] is None:
                    continue
                _numeric(event[key], f"{prefix}.{key}", min_value=0)
        if "rolling_temperature_mean_c" in event:
            _numeric(event["rolling_temperature_mean_c"], f"{prefix}.rolling_temperature_mean_c")
        if "rolling_valid_observations" in event:
            count = event["rolling_valid_observations"]
            _require(type(count) is int and count >= 0,
                     f"{prefix}.rolling_valid_observations must be nonnegative")
            if "rolling_observations" in event:
                _require(count <= event["rolling_observations"],
                         f"{prefix}.rolling_valid_observations exceeds rolling_observations")
        for key in ("rolling_window_ticks", "rolling_observations"):
            if key in event:
                _require(type(event[key]) is int and event[key] > 0,
                         f"{prefix}.{key} must be a positive integer")
        if "rolling_observations" in event and "rolling_window_ticks" in event:
            _require(event["rolling_observations"] <= event["rolling_window_ticks"],
                     f"{prefix}.rolling_observations must not exceed rolling_window_ticks")
        if event.get("spectral_bin_hz") is not None:
            _require(abs(event["spectral_bin_hz"] -
                         event["sample_rate_hz"] / event["sample_count"]) < 1e-5,
                     f"{prefix}.spectral_bin_hz mismatch")
        if event.get("dominant_frequency_hz") is not None:
            _require(event["dominant_frequency_hz"] <= event["sample_rate_hz"] / 2,
                     f"{prefix}.dominant_frequency_hz above Nyquist")
        _numeric(event.get("temperature_c"), f"{prefix}.temperature_c")
        health = event.get("health")
        _require(isinstance(health, str) and health in HEALTH_STATES,
                 f"{prefix}.health has an invalid value")
        if quality == "missing":
            _require(health == "unavailable", f"{prefix}.health must be unavailable for missing data")
            for key in ("rms_g", "peak_to_peak_g", "crest_factor", "spectral_bin_hz",
                        "dominant_frequency_hz", "shaft_1x_amplitude_g", "shaft_2x_amplitude_g",
                        "band_80_400_rms_g", "rolling_rms_mean_g"):
                if key in event:
                    _require(event[key] is None, f"{prefix}.{key} must be null if missing")
        elif quality == "outlier":
            _require(health == "suspect", f"{prefix}.health must be suspect for an outlier")
        else:
            _require(health in ("normal", "warning", "critical"),
                     f"{prefix}.health is inconsistent with good sensor quality")
        reasons = event.get("reasons")
        _require(isinstance(reasons, list) and
                 all(isinstance(x, str) and bool(x) for x in reasons),
                 f"{prefix}.reasons must be a list of nonempty strings")
