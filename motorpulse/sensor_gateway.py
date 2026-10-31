"""MP-057: strict offline physical-sensor capture contract.

This module validates JSON-lines frames already captured from an external device.
It does not open serial ports, sockets, PLC links, or actuators. The contract is
measurement/provenance only and deliberately does not invent fault labels,
health classes, maintenance decisions, failure probabilities, or RUL.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
from math import isfinite
from pathlib import Path
from typing import Any

CAPTURE_VERSION = "1.0.0"
REPORT_VERSION = "1.0.0"
SOURCE = "physical_sensor"
MAX_FRAME_BYTES = 1_048_576
MAX_CAPTURE_BYTES = 268_435_456
MAX_FRAMES = 10_000
MAX_SAMPLES = 65_536
MAX_TEXT = 128
CANONICAL_UNITS = {
    "vibration_acceleration": "g",
    "temperature": "degC",
    "rotational_speed": "rpm",
}
QUALITY_STATES = frozenset({"good", "missing", "outlier"})
QUALITY_CHANNELS = ("vibration", "temperature", "rpm")
PROVENANCE_FIELDS = (
    "device_family",
    "firmware_version",
    "accelerometer_model",
    "temperature_sensor_model",
    "rpm_sensor_model",
)
REQUIRED_FIELDS = frozenset(
    {
        "capture_version",
        "source",
        "device_id",
        "asset_id",
        "sequence",
        "device_uptime_ms",
        "captured_at_utc",
        "sample_rate_hz",
        "sample_count",
        "units",
        "quality",
        "acceleration_g",
        "temperature_c",
        "rpm",
        "provenance",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Invalid sensor frame: {message}")


def _finite(value: Any, field: str, *, nonnegative: bool = False) -> float:
    _require(type(value) in (int, float) and isfinite(value), f"{field} must be finite")
    result = float(value)
    if nonnegative:
        _require(result >= 0, f"{field} must be nonnegative")
    return result


def _text(value: Any, field: str) -> str:
    _require(
        type(value) is str and 0 < len(value) <= MAX_TEXT,
        f"{field} must be 1-{MAX_TEXT} characters",
    )
    _require(
        not any(ord(char) < 32 for char in value),
        f"{field} contains control characters",
    )
    return value


def _utc(value: Any) -> datetime:
    _require(type(value) is str, "captured_at_utc must be a UTC ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Invalid sensor frame: captured_at_utc must be ISO 8601"
        ) from exc
    _require(
        parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0),
        "captured_at_utc must use UTC (+00:00 or Z)",
    )
    return parsed


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key}")
        result[key] = value
    return result


def parse_frame_json(text: str) -> dict[str, Any]:
    """Parse one strict JSON object, rejecting duplicate keys and NaN/Infinity."""
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("invalid sensor-frame JSON") from exc
    if type(value) is not dict:
        raise ValueError("sensor frame must be a JSON object")
    return value


def validate_sensor_frame(frame: dict[str, Any]) -> None:
    """Validate one physical-sensor capture frame without deriving diagnosis."""
    _require(type(frame) is dict, "frame must be an object")
    _require(set(frame) == REQUIRED_FIELDS, "fields must match capture v1 exactly")
    _require(
        frame["capture_version"] == CAPTURE_VERSION,
        f"capture_version must be {CAPTURE_VERSION}",
    )
    _require(frame["source"] == SOURCE, f"source must be {SOURCE}")
    _text(frame["device_id"], "device_id")
    _text(frame["asset_id"], "asset_id")
    sequence = frame["sequence"]
    _require(
        type(sequence) is int and 1 <= sequence < 2**63,
        "sequence must be a positive 64-bit integer",
    )
    uptime = frame["device_uptime_ms"]
    _require(
        type(uptime) is int and 0 <= uptime < 2**63,
        "device_uptime_ms must be a nonnegative 64-bit integer",
    )
    _utc(frame["captured_at_utc"])

    rate = frame["sample_rate_hz"]
    count = frame["sample_count"]
    _require(type(rate) is int and 1 <= rate <= 100_000, "sample_rate_hz out of bounds")
    _require(
        type(count) is int and 1 <= count <= MAX_SAMPLES,
        "sample_count out of bounds",
    )
    _require(
        frame["units"] == CANONICAL_UNITS,
        "units must use the canonical MotorPulse units",
    )

    quality = frame["quality"]
    _require(
        type(quality) is dict and set(quality) == set(QUALITY_CHANNELS),
        "quality must name vibration, temperature and rpm",
    )
    for channel in QUALITY_CHANNELS:
        _require(quality[channel] in QUALITY_STATES, f"quality.{channel} invalid")

    provenance = frame["provenance"]
    _require(
        type(provenance) is dict and set(provenance) == set(PROVENANCE_FIELDS),
        "provenance fields must match capture v1 exactly",
    )
    for field in PROVENANCE_FIELDS:
        _text(provenance[field], f"provenance.{field}")

    acceleration = frame["acceleration_g"]
    if quality["vibration"] == "missing":
        _require(
            acceleration is None,
            "acceleration_g must be null when vibration is missing",
        )
    else:
        _require(
            type(acceleration) is list and len(acceleration) == count,
            "acceleration_g length must equal sample_count",
        )
        for index, value in enumerate(acceleration):
            _finite(value, f"acceleration_g[{index}]")

    temperature = frame["temperature_c"]
    if quality["temperature"] == "missing":
        _require(
            temperature is None,
            "temperature_c must be null when temperature is missing",
        )
    else:
        _finite(temperature, "temperature_c")

    rpm = frame["rpm"]
    if quality["rpm"] == "missing":
        _require(rpm is None, "rpm must be null when rpm is missing")
    else:
        _finite(rpm, "rpm", nonnegative=True)


def current_pipeline_sampling_compatible(frame: dict[str, Any]) -> bool:
    """Return whether a frame can feed the current 1024 Hz/1024-sample feature stage.

    Compatibility here covers only sampling and channel quality. It does not
    claim that a physical sensor is calibrated, comparable to simulation, or
    safe to score with the synthetic anomaly model.
    """
    validate_sensor_frame(frame)
    return (
        frame["sample_rate_hz"] == 1024
        and frame["sample_count"] == 1024
        and all(frame["quality"][channel] == "good" for channel in QUALITY_CHANNELS)
    )


def canonical_frame_bytes(frame: dict[str, Any]) -> bytes:
    """Canonical UTF-8 representation for portable physical-capture hashing."""
    validate_sensor_frame(frame)
    return json.dumps(
        frame,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def validate_capture(path: str | Path) -> dict[str, Any]:
    """Validate a bounded JSONL capture and return a reproducible summary report."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("sensor capture must be an existing non-symlink file")
    size = source.stat().st_size
    if size <= 0 or size > MAX_CAPTURE_BYTES:
        raise ValueError("sensor capture file size is empty or exceeds the limit")

    raw_digest = hashlib.sha256()
    canonical_digest = hashlib.sha256()
    streams: dict[tuple[str, str], tuple[int, int, datetime]] = {}
    device_ids: set[str] = set()
    asset_ids: set[str] = set()
    sampling: set[tuple[int, int]] = set()
    quality_counts: Counter[str] = Counter()
    sequence_gaps = 0
    compatible = 0
    records = 0

    with source.open("rb") as stream:
        while True:
            line = stream.readline(MAX_FRAME_BYTES + 1)
            if not line:
                break
            records += 1
            if records > MAX_FRAMES:
                raise ValueError("sensor capture exceeds the frame-count limit")
            if len(line) > MAX_FRAME_BYTES:
                raise ValueError(f"sensor frame {records} exceeds the byte limit")
            raw_digest.update(line)
            if not line.strip():
                raise ValueError(f"sensor frame {records} is blank")
            try:
                frame = parse_frame_json(line.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise ValueError(f"sensor frame {records} is not UTF-8") from exc
            validate_sensor_frame(frame)
            canonical_digest.update(canonical_frame_bytes(frame))
            canonical_digest.update(b"\n")

            key = (frame["device_id"], frame["asset_id"])
            timestamp = _utc(frame["captured_at_utc"])
            previous = streams.get(key)
            if previous is not None:
                prev_sequence, prev_uptime, prev_timestamp = previous
                if frame["sequence"] <= prev_sequence:
                    raise ValueError(
                        f"sensor stream {key} sequence is not strictly increasing"
                    )
                if frame["device_uptime_ms"] <= prev_uptime:
                    raise ValueError(
                        f"sensor stream {key} uptime is not strictly increasing"
                    )
                if timestamp <= prev_timestamp:
                    raise ValueError(
                        f"sensor stream {key} timestamp is not strictly increasing"
                    )
                sequence_gaps += frame["sequence"] - prev_sequence - 1
            streams[key] = (frame["sequence"], frame["device_uptime_ms"], timestamp)
            device_ids.add(frame["device_id"])
            asset_ids.add(frame["asset_id"])
            sampling.add((frame["sample_rate_hz"], frame["sample_count"]))
            for channel in QUALITY_CHANNELS:
                quality_counts[f"{channel}:{frame['quality'][channel]}"] += 1
            if current_pipeline_sampling_compatible(frame):
                compatible += 1

    if records == 0:
        raise ValueError("sensor capture contains no frames")

    return {
        "report_version": REPORT_VERSION,
        "capture_version": CAPTURE_VERSION,
        "source": SOURCE,
        "records": records,
        "stream_count": len(streams),
        "device_ids": sorted(device_ids),
        "asset_ids": sorted(asset_ids),
        "sequence_gaps": sequence_gaps,
        "sampling_contracts": [
            {"sample_rate_hz": rate, "sample_count": count}
            for rate, count in sorted(sampling)
        ],
        "quality_counts": dict(sorted(quality_counts.items())),
        "current_pipeline_sampling_compatible_frames": compatible,
        "input_sha256": raw_digest.hexdigest(),
        "canonical_frames_sha256": canonical_digest.hexdigest(),
        "claims": {
            "physical_measurement": True,
            "field_calibrated": False,
            "diagnosis": False,
            "failure_probability": False,
            "rul": False,
        },
    }


def write_report(report: dict[str, Any], path: str | Path) -> None:
    """Write one report without overwriting an existing file."""
    destination = Path(path)
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError(
            "report parent directory must already exist and not be a symlink"
        )
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                report,
                stream,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            stream.write("\n")
    except FileExistsError as exc:
        raise ValueError("report output already exists; refusing to overwrite") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an offline MotorPulse physical-sensor JSONL capture"
    )
    parser.add_argument("capture", help="local JSONL capture file")
    parser.add_argument(
        "--out-report", help="optional write-once JSON validation report"
    )
    args = parser.parse_args(argv)
    report = validate_capture(args.capture)
    if args.out_report:
        write_report(report, args.out_report)
    else:
        print(json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
