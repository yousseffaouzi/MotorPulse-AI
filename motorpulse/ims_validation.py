"""MP-028: local-only IMS validation and train-only preprocessing.

Input is a report returned by motorpulse.ims.inspect_ims_directory. No archive
downloads, inferred labels, UTC conversion, resampling or unit conversion.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from math import isfinite, sqrt
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ims import MAX_FILE_BYTES, SOURCE_CARD_ID, TIMESTAMP_PATTERN, _local_timestamp, _read_strict_json, write_local_manifest

FEATURE_KEYS = ("rms_native", "peak_to_peak_native", "crest_factor")
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_REPORT_RECORDS = 100
MAX_QUALITY_ISSUES = 10000


def _numeric(value: Any, label: str, *, minimum: float | None = None) -> float:
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return float(value)


def _integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")
    return value


def _issue(issues: list[dict], code: str, severity: str, *, filename: str | None = None,
           channel: str | None = None, detail: str = "") -> None:
    if len(issues) >= MAX_QUALITY_ISSUES:
        raise ValueError("quality report exceeds issue limit")
    issues.append({"code": code, "severity": severity, "filename": filename,
                   "channel_id": channel, "detail": detail})


def validate_ims_report(report: Mapping[str, Any], *,
                        expected_interval_s: float | None = None,
                        verify_files: bool = False,
                        crest_review_threshold: float = 6.0) -> dict:
    """Return deterministic quality summary or reject structurally corrupt reports.

    Flatlined/high-crest flags are *review prompts*, not diagnoses. Filename
    timestamps remain naive (unknown time zone); no UTC is inferred.
    """
    if not isinstance(report, Mapping) or report.get("source_card_id") != SOURCE_CARD_ID:
        raise ValueError("not an IMS source-card local report")
    if report.get("data_source") != "user_supplied_local_ims_style":
        raise ValueError("unexpected data source")
    if report.get("publication_status") != "local_only_do_not_redistribute":
        raise ValueError("local-only publication policy required")
    test_set = report.get("test_set")
    if test_set not in ("1", "2", "3") or report.get("run_id") != f"ims-set-{test_set}":
        raise ValueError("test-set/run-id mismatch")
    count = _integer(report.get("samples_per_record_declared"), "sample count", 1, 32768)
    channels = _integer(report.get("channels_per_record_declared"), "channel count", 1, 16)
    fs = _numeric(report.get("sample_rate_hz_declared"), "sample rate", minimum=1)
    if fs > 1_000_000:
        raise ValueError("sample rate too large")
    unit = report.get("value_unit_declared")
    if unit not in ("unknown", "g", "m/s^2", "V"):
        raise ValueError("unrecognized native unit")
    duration = _numeric(report.get("snapshot_duration_s"), "snapshot duration", minimum=0)
    if abs(duration - count / fs) > 1e-9:
        raise ValueError("duration does not match declared sampling rate")
    if report.get("timestamp_timezone") != "unknown":
        raise ValueError("cannot assert UTC or a time zone for the raw IMS filenames")
    if expected_interval_s is not None:
        _numeric(expected_interval_s, "expected interval", minimum=1e-12)
        if expected_interval_s <= 0:
            raise ValueError("expected interval must be positive")
    _numeric(crest_review_threshold, "crest threshold", minimum=1)
    records = report.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_REPORT_RECORDS:
        raise ValueError("records must be a nonempty bounded list")
    if report.get("record_count") != len(records) or report.get("channel_record_count") != len(records) * channels:
        raise ValueError("record/channel counts do not match")
    mapping = report.get("channel_mapping")
    if mapping is not None:
        if not isinstance(mapping, dict) or mapping.get("test_set") != test_set or not isinstance(mapping.get("channels"), dict):
            raise ValueError("invalid channel mapping in report")
        if set(mapping["channels"]) != {str(i) for i in range(1, channels + 1)}:
            raise ValueError("channel mapping missing entries")
    issues: list[dict] = []
    prev: datetime | None = None
    seen: set[str] = set()
    directory = None
    if verify_files:
        directory_value = report.get("input_directory")
        if type(directory_value) is not str or not directory_value.strip():
            raise ValueError("source input directory must be an absolute local directory path")
        directory = Path(directory_value)
        if not directory.is_absolute():
            raise ValueError("source input directory must be absolute")
    if verify_files and (not directory.is_dir() or directory.is_symlink()):
        raise ValueError("source report input directory is missing or symlinked")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("record must be an object")
        filename = record.get("filename")
        if not isinstance(filename, str) or not TIMESTAMP_PATTERN.fullmatch(filename):
            raise ValueError("invalid filename in report")
        timestamp = _local_timestamp(filename)
        if filename in seen:
            raise ValueError("duplicate record filename")
        seen.add(filename)
        if record.get("timestamp_local") != timestamp.isoformat() or record.get("timezone") != "unknown; no UTC conversion":
            raise ValueError(f"timestamp/time-zone mismatch: {filename}")
        if record.get("run_id") != report["run_id"] or record.get("test_set") != test_set:
            raise ValueError(f"unexpected run/test group in {filename}")
        if prev is not None:
            delta = (timestamp - prev).total_seconds()
            if delta <= 0:
                raise ValueError(f"timestamps must be strictly increasing: {filename}")
            if expected_interval_s is not None and abs(delta - expected_interval_s) > max(.001, expected_interval_s*.05):
                _issue(issues, "cadence_deviation", "warning", filename=filename,
                       detail=f"interval={delta:g}s, declared_expected={expected_interval_s:g}s")
            if delta < duration:
                _issue(issues, "window_overlap", "warning", filename=filename,
                       detail="timestamp spacing shorter than declared window duration")
        prev = timestamp
        if record.get("sample_count") != count:
            raise ValueError(f"sample count mismatch: {filename}")
        _integer(record.get("bytes"), f"byte count: {filename}", 1, MAX_FILE_BYTES)
        sha = record.get("sha256")
        if type(sha) is not str or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError(f"invalid lowercase SHA-256: {filename}")
        rows = record.get("channels")
        if not isinstance(rows, list) or len(rows) != channels:
            raise ValueError(f"channel count mismatch: {filename}")
        if verify_files:
            source = directory / filename
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"missing/unsafe source: {filename}")
            h = hashlib.sha256()
            size = 0
            with source.open("rb") as file:
                for chunk in iter(lambda: file.read(65536), b""):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise ValueError(f"source file exceeds size limit: {filename}")
                    h.update(chunk)
            if h.hexdigest() != sha or size != record["bytes"]:
                raise ValueError(f"source checksum/size mismatch: {filename}")
        for i, row in enumerate(rows, 1):
            ch = f"ch-{i:02d}"
            if not isinstance(row, dict) or row.get("channel_id") != ch:
                raise ValueError(f"channel ordering mismatch in {filename}")
            if row.get("group_key") != f"ims:set-{test_set}:ch-{i:02d}":
                raise ValueError(f"channel group key mismatch: {filename}")
            if row.get("value_unit") != unit:
                raise ValueError(f"native unit mismatch: {filename}, {ch}")
            if row.get("bearing_id") != (mapping["channels"][str(i)] if mapping else None):
                raise ValueError(f"channel-bearing mapping mismatch: {filename}, {ch}")
            rms = _numeric(row.get("rms_native"), "RMS", minimum=0)
            ptp = _numeric(row.get("peak_to_peak_native"), "peak-to-peak", minimum=0)
            crest = _numeric(row.get("crest_factor"), "crest factor", minimum=0)
            if rms == 0 and (ptp != 0 or crest != 0):
                raise ValueError(f"inconsistent zero RMS in {filename}, {ch}")
            if rms > 0 and crest < 1 - 1e-8:
                raise ValueError(f"crest factor below 1 in {filename}, {ch}")
            if ptp == 0:
                _issue(issues, "flatline_review", "warning", filename=filename, channel=ch,
                       detail="constant-valued samples; may be valid constant offset or faulty sensor")
            if crest >= crest_review_threshold:
                _issue(issues, "high_crest_review", "warning", filename=filename, channel=ch,
                       detail="large crest factor; not proof of a bearing defect")
            if unit == "unknown":
                _issue(issues, "unit_unverified", "info", filename=filename, channel=ch,
                       detail="physical measurement unit not established by donor documentation")
            if row.get("bearing_id") is None:
                _issue(issues, "bearing_mapping_unverified", "info", filename=filename, channel=ch,
                       detail="no documented mapping supplied; bearing identity unknown")
    # Enforce no claims about unknown machine failures in an inspection report.
    truth = report.get("ground_truth")
    if not isinstance(truth, dict) or any(truth.get(k) is not None for k in (
        "window_fault_label", "fault_onset_time", "rul_seconds")):
        raise ValueError("local inspection must not invent window-level failure truth")
    issues.sort(key=lambda x: (x["filename"] or "", x["channel_id"] or "", x["code"]))
    by_code: dict[str, int] = {}
    for item in issues:
        by_code[item["code"]] = by_code.get(item["code"], 0) + 1
    return {
        "validation_version": "1.0.0",
        "source_card_id": SOURCE_CARD_ID,
        "run_id": report["run_id"],
        "source_report_record_count": len(records),
        "channel_record_count": len(records)*channels,
        "sample_rate_hz_declared": fs,
        "nyquist_hz_declared": fs / 2,
        "frequency_bin_hz_declared": fs / count,
        "samples_per_record_declared": count,
        "value_unit_declared": unit,
        "timestamp_timezone": "unknown",
        "verified_file_checksums": verify_files,
        "quality_issues": issues,
        "counts_by_issue": dict(sorted(by_code.items())),
        "diagnostic_claims": "none; flags are review prompts, not failure labels",
        "publication_status": "local_only_do_not_redistribute",
    }


def _run_id(report: Mapping) -> str:
    if not isinstance(report, Mapping) or not isinstance(report.get("run_id"), str):
        raise ValueError("reports must have a run_id")
    return report["run_id"]


def fit_train_scaler(train_reports: Sequence[dict], heldout_reports: Sequence[dict]) -> dict:
    """Fit z-score parameters only on whole training runs, never held-out data.

    Requires a nonempty explicitly disjoint held-out run, and homogeneous
    unit/sample-rate/sample-count. No imputation or feature selection occurs.
    """
    if not train_reports or not heldout_reports:
        raise ValueError("at least one complete train and held-out run required")
    train_runs = [_run_id(r) for r in train_reports]
    heldout_runs = [_run_id(r) for r in heldout_reports]
    if len(set(train_runs+heldout_runs)) != len(train_runs)+len(heldout_runs):
        raise ValueError("run overlap/duplicate: training and held-out runs must be disjoint")
    all_reports = list(train_reports) + list(heldout_reports)
    for report in all_reports:
        validate_ims_report(report)
    units = {r["value_unit_declared"] for r in all_reports}
    rates = {r["sample_rate_hz_declared"] for r in all_reports}
    counts = {r["samples_per_record_declared"] for r in all_reports}
    if len(units) != 1 or len(rates) != 1 or len(counts) != 1:
        raise ValueError("cannot normalize runs with different units, sample rates or window sizes")
    if "unknown" in units:
        raise ValueError("unit must be verified before combining runs")
    values = {key: [] for key in FEATURE_KEYS}
    for report in train_reports:
        for record in report["records"]:
            for channel in record["channels"]:
                for key in FEATURE_KEYS:
                    values[key].append(float(channel[key]))
    parameters = {}
    for key, numbers in values.items():
        mean = sum(numbers) / len(numbers)
        std = sqrt(sum((x-mean)**2 for x in numbers)/len(numbers))
        parameters[key] = {"mean": mean, "std": std, "constant": std == 0}
    return {
        "scaler_version": "1.0.0", "fit_on": "training_runs_only",
        "train_run_ids": sorted(train_runs), "heldout_run_ids": sorted(heldout_runs),
        "source_card_id": SOURCE_CARD_ID, "features": list(FEATURE_KEYS),
        "sample_rate_hz_declared": next(iter(rates)),
        "samples_per_record_declared": next(iter(counts)),
        "value_unit_declared": next(iter(units)),
        "parameters": parameters, "publication_status": "local_only_do_not_redistribute",
    }


def transform_report(report: dict, scaler: dict, *, partition: str) -> list[dict]:
    """Transform *features* only, preserving grouping and sensor provenance."""
    if partition not in ("train", "heldout"):
        raise ValueError("partition must be train or heldout")
    validate_ims_report(report)
    run = report["run_id"]
    expected = scaler["train_run_ids" if partition == "train" else "heldout_run_ids"]
    if run not in expected:
        raise ValueError("run not declared in scaler partition")
    for key in ("source_card_id", "value_unit_declared", "sample_rate_hz_declared",
                "samples_per_record_declared"):
        if scaler.get(key) != report.get(key):
            raise ValueError(f"incompatible scaler provenance field: {key}")
    result = []
    for rec in report["records"]:
        for channel in rec["channels"]:
            normalized = {}
            for key in FEATURE_KEYS:
                p = scaler["parameters"][key]
                normalized[key+"_z"] = ((channel[key] - p["mean"]) / p["std"]
                                        if p["std"] > 0 else 0.0)
            result.append({
                "run_id": run, "group_key": channel["group_key"],
                "bearing_id": channel["bearing_id"], "channel_id": channel["channel_id"],
                "timestamp_local": rec["timestamp_local"], "timezone": "unknown",
                "source_sha256": rec["sha256"], "partition": partition,
                **normalized
            })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local IMS inspection reports without uploading or republishing data")
    parser.add_argument("--report", type=Path, required=True, help="existing report from motorpulse-ims")
    parser.add_argument("--expected-interval-s", type=float, help="optional filename cadence expectation")
    parser.add_argument("--verify-files", action="store_true", help="recompute local record checksums")
    parser.add_argument("--out", type=Path, help="new, local-only validation report; never overwrites")
    args = parser.parse_args()
    try:
        report = _read_strict_json(args.report, MAX_REPORT_BYTES)
        result = validate_ims_report(report, expected_interval_s=args.expected_interval_s,
                                     verify_files=args.verify_files)
        if args.out:
            write_local_manifest(args.out, result)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Checked {result['source_report_record_count']} snapshots / "
          f"{result['channel_record_count']} channels, "
          f"{len(result['quality_issues'])} quality flags; no defect labels inferred.")
    if args.out:
        print(f"Local validation report: {args.out}")


if __name__ == "__main__":
    main()
