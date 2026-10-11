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
HEALTH_STATES = frozenset({"normal", "warning", "critical"})


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
        for key in ("rpm", "rms_g", "peak_to_peak_g", "crest_factor"):
            _numeric(event.get(key), f"{prefix}.{key}", min_value=0)
        if "shaft_frequency_hz" in event:
            _numeric(event["shaft_frequency_hz"], f"{prefix}.shaft_frequency_hz", min_value=0)
            _require(abs(event["shaft_frequency_hz"] - event["rpm"] / 60) <= 0.001,
                     f"{prefix}.shaft_frequency_hz must correspond to rpm / 60")
        _numeric(event.get("temperature_c"), f"{prefix}.temperature_c")
        health = event.get("health")
        _require(isinstance(health, str) and health in HEALTH_STATES,
                 f"{prefix}.health must be normal, warning or critical")
        reasons = event.get("reasons")
        _require(isinstance(reasons, list) and
                 all(isinstance(x, str) and bool(x) for x in reasons),
                 f"{prefix}.reasons must be a list of nonempty strings")
