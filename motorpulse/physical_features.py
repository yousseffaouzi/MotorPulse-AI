"""Offline feature extraction for validated physical-sensor captures.

MP-058 converts MP-057 capture frames into deterministic feature rows. It does
not classify machinery, score the synthetic anomaly model, train a model, or
open serial/network/PLC/actuator connections.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from math import sqrt
from pathlib import Path
from typing import Any

from .sensor_gateway import (
    MAX_FRAME_BYTES,
    canonical_frame_bytes,
    current_pipeline_sampling_compatible,
    parse_frame_json,
    validate_capture,
    validate_sensor_frame,
)
from .spectral import spectral_features

FEATURE_VERSION = "1.0.0"
REPORT_VERSION = "1.0.0"
FEATURE_SOURCE = "physical_sensor_features"
FEATURE_KEYS = (
    "rms_g",
    "peak_to_peak_g",
    "crest_factor",
    "spectral_bin_hz",
    "dominant_frequency_hz",
    "shaft_1x_amplitude_g",
    "shaft_2x_amplitude_g",
    "band_80_400_rms_g",
)


def _time_domain_features(samples: list[float]) -> dict[str, float]:
    if not samples:
        raise ValueError("physical vibration samples must not be empty")
    rms = sqrt(sum(value * value for value in samples) / len(samples))
    peak = max(abs(value) for value in samples)
    return {
        "rms_g": round(rms, 4),
        "peak_to_peak_g": round(max(samples) - min(samples), 4),
        "crest_factor": round(peak / rms, 4) if rms else 0.0,
    }


def _abstention_reasons(frame: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if frame["sample_rate_hz"] != 1024 or frame["sample_count"] != 1024:
        reasons.append("current feature contract requires 1024 Hz and 1024 samples")
    for channel in ("vibration", "temperature", "rpm"):
        quality = frame["quality"][channel]
        if quality != "good":
            reasons.append(f"{channel} quality is {quality}")
    rpm = frame["rpm"]
    if frame["quality"]["rpm"] == "good" and rpm == 0:
        reasons.append("rpm must be positive for shaft-referenced spectral features")
    return reasons


def extract_frame_features(frame: dict[str, Any]) -> dict[str, Any]:
    """Derive one provenance-preserving feature row without model scoring."""
    validate_sensor_frame(frame)
    rpm = frame["rpm"]
    ready = current_pipeline_sampling_compatible(frame) and rpm != 0
    reasons = [] if ready else _abstention_reasons(frame)
    result: dict[str, Any] = {
        "feature_version": FEATURE_VERSION,
        "source": FEATURE_SOURCE,
        "measurement_source": frame["source"],
        "device_id": frame["device_id"],
        "asset_id": frame["asset_id"],
        "sequence": frame["sequence"],
        "device_uptime_ms": frame["device_uptime_ms"],
        "captured_at_utc": frame["captured_at_utc"],
        "sample_rate_hz": frame["sample_rate_hz"],
        "sample_count": frame["sample_count"],
        "units": dict(frame["units"]),
        "quality": dict(frame["quality"]),
        "temperature_c": frame["temperature_c"],
        "rpm": rpm,
        "provenance": dict(frame["provenance"]),
        "input_frame_sha256": hashlib.sha256(canonical_frame_bytes(frame)).hexdigest(),
        "feature_status": "extracted" if ready else "abstained",
        "feature_status_reasons": reasons,
        "spectral_window": "hann" if ready else None,
    }
    if not ready:
        result.update({key: None for key in FEATURE_KEYS})
        return result

    samples = frame["acceleration_g"]
    assert isinstance(samples, list)
    assert isinstance(rpm, (int, float))
    result.update(_time_domain_features(samples))
    result.update(spectral_features(samples, rpm, sample_rate_hz=frame["sample_rate_hz"]))
    return result


def canonical_feature_bytes(row: dict[str, Any]) -> bytes:
    return json.dumps(
        row,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_unchanged_validated_frames(
    path: Path, capture_report: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_digest = hashlib.sha256()
    canonical_digest = hashlib.sha256()
    frames: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        while True:
            line = stream.readline(MAX_FRAME_BYTES + 1)
            if not line:
                break
            raw_digest.update(line)
            try:
                frame = parse_frame_json(line.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise ValueError("sensor capture changed to non-UTF-8 data") from exc
            validate_sensor_frame(frame)
            canonical_digest.update(canonical_frame_bytes(frame))
            canonical_digest.update(b"\n")
            frames.append(frame)
    if raw_digest.hexdigest() != capture_report["input_sha256"]:
        raise ValueError("sensor capture changed during feature extraction")
    if canonical_digest.hexdigest() != capture_report["canonical_frames_sha256"]:
        raise ValueError("canonical sensor capture changed during feature extraction")
    return frames


def extract_capture(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate one capture and derive deterministic feature rows and a report."""
    source = Path(path)
    capture_report = validate_capture(source)
    frames = _load_unchanged_validated_frames(source, capture_report)
    rows = [extract_frame_features(frame) for frame in frames]
    feature_digest = hashlib.sha256()
    status_counts: Counter[str] = Counter()
    for row in rows:
        feature_digest.update(canonical_feature_bytes(row))
        feature_digest.update(b"\n")
        status_counts[row["feature_status"]] += 1
    report = {
        "report_version": REPORT_VERSION,
        "feature_version": FEATURE_VERSION,
        "source": FEATURE_SOURCE,
        "records": len(rows),
        "feature_status_counts": dict(sorted(status_counts.items())),
        "input_sha256": capture_report["input_sha256"],
        "canonical_frames_sha256": capture_report["canonical_frames_sha256"],
        "features_sha256": feature_digest.hexdigest(),
        "claims": {
            "physical_features": True,
            "field_calibrated": False,
            "training_authorized": False,
            "model_scoring_authorized": False,
            "diagnosis": False,
            "failure_probability": False,
            "rul": False,
        },
    }
    return rows, report


def _require_new_output(path: Path, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"{label} output already exists; refusing to overwrite")
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError(f"{label} output parent must exist and not be a symlink")


def write_feature_outputs(
    rows: list[dict[str, Any]],
    report: dict[str, Any],
    features_path: str | Path,
    report_path: str | Path,
) -> None:
    """Write deterministic JSONL features and JSON report without overwriting."""
    features_destination = Path(features_path)
    report_destination = Path(report_path)
    if features_destination == report_destination:
        raise ValueError("feature and report output paths must be different")
    _require_new_output(features_destination, "feature")
    _require_new_output(report_destination, "report")
    feature_bytes = b"".join(canonical_feature_bytes(row) + b"\n" for row in rows)
    created_feature = False
    try:
        with features_destination.open("xb") as stream:
            stream.write(feature_bytes)
        created_feature = True
        with report_destination.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                report,
                stream,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            stream.write("\n")
    except Exception:
        if created_feature:
            features_destination.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract non-diagnostic features from an offline physical capture"
    )
    parser.add_argument("capture", help="validated MP-057 JSONL capture")
    parser.add_argument("--out-features", required=True, help="write-once feature JSONL")
    parser.add_argument("--out-report", required=True, help="write-once summary JSON")
    args = parser.parse_args(argv)
    rows, report = extract_capture(args.capture)
    write_feature_outputs(rows, report, args.out_features, args.out_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
