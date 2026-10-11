"""MP-029: bounded, deterministic data-quality summaries for synthetic and local IMS data.

No downloads, trained predictions, chart dependencies, or third-party files.
The output is a descriptive report, not a bearing diagnosis.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from math import isfinite, sqrt
from pathlib import Path
import statistics
from typing import Any

from .ims import _read_strict_json, write_local_manifest
from .ims_validation import FEATURE_KEYS, MAX_REPORT_BYTES, validate_ims_report

MAX_SYNTHETIC_EVENTS = 12000
MAX_LINE_BYTES = 16384
MAX_SYNTHETIC_FILE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
MAX_GROUPS = 16
MAX_TREND_POINTS = 12
SYNTHETIC_FEATURES = ("rms_g", "temperature_c", "rpm",
                      "crest_factor", "band_80_400_rms_g")
VIBRATION_FIELDS = frozenset(("rms_g", "crest_factor", "band_80_400_rms_g"))


def _json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"nonfinite JSON literal: {value}")
    def unique(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique)


def _file_digest(path: Path, limit: int) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing or unsafe data file: {path.name}")
    if path.stat().st_size > limit:
        raise ValueError(f"data file too large: {path.name}")
    size = 0
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for block in iter(lambda: fp.read(65536), b""):
            size += len(block)
            if size > limit:
                raise ValueError(f"data file exceeds size limit: {path.name}")
            h.update(block)
    return h.hexdigest(), size


def _percentile(sorted_values: list[float], fraction: float) -> float:
    index = (len(sorted_values) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (index - lower)


def _describe(values: list[float], total_count: int) -> dict[str, Any]:
    ordered = sorted(values)
    base: dict[str, Any] = {"count": len(ordered),
                            "missing_count": total_count - len(ordered)}
    if not ordered:
        base.update({k: None for k in ("min", "p05", "median", "mean", "p95", "max", "std")})
        return base
    mean = statistics.fmean(ordered)
    base.update({
        "min": ordered[0], "p05": _percentile(ordered, .05),
        "median": _percentile(ordered, .5), "mean": mean,
        "p95": _percentile(ordered, .95), "max": ordered[-1],
        "std": sqrt(sum((v - mean) ** 2 for v in ordered) / len(ordered)),
    })
    if not all(v is None or isfinite(v) for v in base.values()):
        raise ValueError("nonfinite summary")
    return base


def _feature_number(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{name} must be a finite numeric reading or null")
    return float(value)


def _select_trend(points: list[dict]) -> list[dict]:
    if len(points) <= MAX_TREND_POINTS:
        return points
    half = MAX_TREND_POINTS // 2
    return points[:half] + points[-half:]


def _ordered_counts(counter: Counter) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def synthetic_quality_report(folder: str | Path) -> dict:
    """Summarize a synthetic export whose lossless JSONL and manifest hashes match.

    CSV-only exports have no lossless typed representation, and are rejected
    explicitly; generate --format jsonl or both for reproducible EDA.
    """
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("dataset must be a local, non-symlink directory")
    manifest = _read_strict_json(folder / "manifest.json", MAX_MANIFEST_BYTES)
    if not isinstance(manifest, dict) or manifest.get("dataset_type") != "synthetic_motor_feature_events":
        raise ValueError("not a MotorPulse synthetic export manifest")
    if manifest.get("synthetic_only") is not True or manifest.get("schema_version") != "1.0.0":
        raise ValueError("unsupported synthetic export contract")
    events_expected = manifest.get("events")
    ticks_expected = manifest.get("ticks")
    assets_expected = manifest.get("assets")
    if (type(events_expected) is not int or not 1 <= events_expected <= MAX_SYNTHETIC_EVENTS or
            type(ticks_expected) is not int or ticks_expected < 1 or
            type(assets_expected) is not int or not 1 <= assets_expected <= 12 or
            events_expected != ticks_expected * assets_expected):
        raise ValueError("invalid event/tick/motor cardinality")
    files = manifest.get("files")
    if not isinstance(files, dict) or "events.jsonl" not in files:
        raise ValueError("lossless events.jsonl is required (export with --format jsonl or both)")
    for name, meta in files.items():
        if name not in ("events.csv", "events.jsonl") or not isinstance(meta, dict):
            raise ValueError("unexpected file in export manifest")
        if (type(meta.get("bytes")) is not int or meta["bytes"] < 1 or
                meta["bytes"] > MAX_SYNTHETIC_FILE_BYTES or
                not isinstance(meta.get("sha256"), str)):
            raise ValueError("invalid file digest metadata")
        digest, size = _file_digest(folder / name, MAX_SYNTHETIC_FILE_BYTES)
        if digest != meta["sha256"] or size != meta["bytes"]:
            raise ValueError(f"export file integrity check failed: {name}")
    export_id = manifest.get("export_id")
    if not isinstance(export_id, str) or not export_id.startswith("sim-"):
        raise ValueError("invalid export identity")
    raw_by_asset: dict[str, dict[str, Any]] = {}
    saw: set[tuple[int, str]] = set()
    next_tick = 1
    events_seen = 0
    file = folder / "events.jsonl"
    with file.open("rb") as stream:
        while True:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LINE_BYTES:
                raise ValueError("JSONL event line too long")
            events_seen += 1
            if events_seen > events_expected:
                raise ValueError("too many events in JSONL")
            try:
                item = _json(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid JSONL event at line {events_seen}") from exc
            if not isinstance(item, dict):
                raise ValueError("event must be an object")
            tick = item.get("tick")
            asset = item.get("asset_id")
            if (item.get("export_id") != export_id or item.get("source") != "synthetic" or
                    item.get("schema_version") != "1.0.0" or
                    type(tick) is not int or tick < 1 or tick > ticks_expected or
                    not isinstance(asset, str) or not asset or len(asset) > 64):
                raise ValueError("invalid event provenance or tick/asset identity")
            if tick < next_tick or tick > next_tick + 1 or (tick, asset) in saw:
                raise ValueError("duplicate or nonchronological event")
            next_tick = tick
            saw.add((tick, asset))
            if asset not in raw_by_asset:
                if len(raw_by_asset) >= MAX_GROUPS:
                    raise ValueError("too many assets")
                raw_by_asset[asset] = {"features": defaultdict(list),
                                       "counts": Counter(), "sensor": Counter(),
                                       "health": Counter(), "trend": [],
                                       "count": 0, "last_tick": 0}
            group = raw_by_asset[asset]
            if tick <= group["last_tick"]:
                raise ValueError("asset tick repeats or reverses")
            group["last_tick"] = tick
            quality = item.get("sensor_quality")
            health = item.get("health")
            scenario = item.get("scenario")
            if quality not in ("good", "missing", "outlier") or health not in (
                "normal", "warning", "critical", "unavailable", "suspect"):
                raise ValueError("invalid health or sensor-quality label")
            if quality == "missing" and health != "unavailable":
                raise ValueError("missing sensor must suppress health")
            if quality == "outlier" and health != "suspect":
                raise ValueError("outlier must suppress health")
            if quality == "good" and health in ("unavailable", "suspect"):
                raise ValueError("good sensor incompatible with unknown assessment")
            if scenario not in ("healthy", "imbalance", "bearing_wear", "misalignment", "overload"):
                raise ValueError("unrecognized synthetic motor truth")
            timestamp = item.get("timestamp_utc")
            if not isinstance(timestamp, str) or not timestamp.endswith("+00:00"):
                raise ValueError("synthetic timestamp must be UTC")
            features = {}
            for key in SYNTHETIC_FEATURES:
                value = _feature_number(item.get(key), key)
                if quality == "missing" and key in VIBRATION_FIELDS and value is not None:
                    raise ValueError("missing vibration should be JSON null")
                if quality != "missing" and value is None:
                    raise ValueError("unexpected null feature")
                if value is not None:
                    group["features"][key].append(value)
                features[key] = value
            group["count"] += 1
            group["counts"][scenario] += 1
            group["health"][health] += 1
            group["sensor"][quality] += 1
            group["trend"].append({"tick": tick, "timestamp_utc": timestamp,
                                   "rms_g": features["rms_g"],
                                   "temperature_c": features["temperature_c"]})
    if events_seen != events_expected or len(raw_by_asset) != assets_expected or next_tick != ticks_expected:
        raise ValueError("event count, asset count or tick range mismatch")
    per_asset = {}
    for asset, group in sorted(raw_by_asset.items()):
        if group["count"] != ticks_expected or group["last_tick"] != ticks_expected:
            raise ValueError(f"incomplete tick history for asset: {asset}")
        per_asset[asset] = {
            "observations": group["count"],
            "synthetic_fault_truth_counts": _ordered_counts(group["counts"]),
            "sensor_quality_counts": _ordered_counts(group["sensor"]),
            "heuristic_health_counts": _ordered_counts(group["health"]),
            "features": {k: _describe(group["features"][k], group["count"])
                         for k in SYNTHETIC_FEATURES},
            "trend_sample_first_last": _select_trend(group["trend"]),
        }
    return {
        "report_version": "1.0.0",
        "source_type": "synthetic_motor_feature_events",
        "synthetic_only": True, "publication_status": "synthetic_demo",
        "export_id": export_id,
        "source_file_sha256": files["events.jsonl"]["sha256"],
        "model_source_sha256": manifest.get("model_source_sha256"),
        "config_sha256": manifest.get("config_sha256"),
        "virtual_start_utc": manifest.get("virtual_start_utc"),
        "virtual_end_utc": manifest.get("virtual_end_utc"),
        "sample_rate_hz": manifest.get("sample_rate_hz"),
        "sample_count": manifest.get("sample_count"),
        "events": events_seen, "ticks": ticks_expected, "assets": assets_expected,
        "units": {"rms_g": "g RMS", "temperature_c": "degrees C", "rpm": "RPM",
                  "crest_factor": "dimensionless", "band_80_400_rms_g": "g RMS"},
        "per_asset": per_asset,
        "label_note": "scenario is programmed synthetic ground truth; health is an uncalibrated rule output",
        "quality_note": "missing vibration is null, not zero; sensor outliers are injected, not detected",
        "trend_note": "first and last 6 windows only for each asset, not an exhaustive plot",
    }


def ims_quality_report(source: dict, *, verify_files: bool = False,
                       expected_interval_s: float | None = None) -> dict:
    """Build an in-memory local-only report from an MP-009 inspection report."""
    quality = validate_ims_report(source, verify_files=verify_files,
                                  expected_interval_s=expected_interval_s)
    groups: dict[str, dict] = {}
    for record in source["records"]:
        for ch in record["channels"]:
            key = ch["group_key"]
            if key not in groups:
                groups[key] = {"channel_id": ch["channel_id"],
                               "bearing_id": ch["bearing_id"],
                               "values": defaultdict(list), "trend": []}
            group = groups[key]
            for feature in FEATURE_KEYS:
                group["values"][feature].append(_feature_number(ch[feature], feature))
            group["trend"].append({
                "timestamp_local": record["timestamp_local"],
                "rms_native": ch["rms_native"],
            })
    by_channel = {}
    for key, group in sorted(groups.items()):
        by_channel[key] = {
            "channel_id": group["channel_id"], "bearing_id": group["bearing_id"],
            "features": {name: _describe(group["values"][name], len(source["records"]))
                         for name in FEATURE_KEYS},
            "trend_sample_first_last": _select_trend(group["trend"]),
        }
    return {
        "report_version": "1.0.0",
        "source_type": "user_supplied_local_ims_style",
        "synthetic_only": False,
        "publication_status": "local_only_do_not_redistribute",
        "source_card_id": source["source_card_id"],
        "run_id": source["run_id"], "test_set": source["test_set"],
        "record_count": source["record_count"],
        "channel_record_count": source["channel_record_count"],
        "original_archive_sha256": source["original_archive_sha256"],
        "acquired_on": source["acquired_on"],
        "sample_rate_hz_declared": source["sample_rate_hz_declared"],
        "samples_per_record_declared": source["samples_per_record_declared"],
        "snapshot_duration_s": source["snapshot_duration_s"],
        "value_unit_declared": source["value_unit_declared"],
        "timestamp_timezone": "unknown; no UTC conversion",
        "verification": {"file_hashes_rechecked": quality["verified_file_checksums"],
                         "issues_by_code": quality["counts_by_issue"]},
        "per_channel": by_channel,
        "ground_truth": {"window_fault_label": None, "fault_onset_time": None,
                         "rul_seconds": None},
        "label_note": "real experimental records: no validated per-window defect label or onset is provided",
        "quality_note": "flatline, high crest, missing bearing map or unknown units are review prompts, not diagnoses",
        "trend_note": "first and last 6 acquisition timestamps only; native timezone is unknown",
    }


def _safe_cell(value: Any) -> str:
    # Markdown is a human-readable interpretation, not a safe HTML container.
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown(report: dict) -> str:
    """Deterministic, readable Markdown with summary tables and trend samples."""
    lines = ["# MotorPulse AI — Exploratory data quality", "",
             f"**Source:** {_safe_cell(report['source_type'])}",
             f"**Publication:** {_safe_cell(report['publication_status'])}", "",
             f"> {_safe_cell(report['label_note'])}", "",
             f"> {_safe_cell(report['quality_note'])}", ""]
    if report["synthetic_only"]:
        lines += [f"**Export ID:** {_safe_cell(report['export_id'])}",
                  f"**Records:** {report['events']} across {report['assets']} motors and {report['ticks']} ticks",
                  "", "## Per-motor summary", ""]
        for asset, group in report["per_asset"].items():
            lines += [f"### {_safe_cell(asset)}", "",
                      "Metric | Count | Missing | Mean | Median | P05 | P95",
                      "--- | ---: | ---: | ---: | ---: | ---: | ---:"]
            for key, summary in group["features"].items():
                lines.append(f"{_safe_cell(key)} | {summary['count']} | {summary['missing_count']} | "
                             f"{summary['mean']} | {summary['median']} | {summary['p05']} | {summary['p95']}")
            lines += ["", f"Synthetic fault truth: {_safe_cell(group['synthetic_fault_truth_counts'])}",
                      f"Sensor quality: {_safe_cell(group['sensor_quality_counts'])}",
                      f"Rule-based health: {_safe_cell(group['heuristic_health_counts'])}",
                      "", "Tick | UTC | RMS (g) | Temperature (C)",
                      "---: | --- | ---: | ---:"]
            for point in group["trend_sample_first_last"]:
                lines.append(f"{point['tick']} | {_safe_cell(point['timestamp_utc'])} | "
                             f"{point['rms_g']} | {point['temperature_c']}")
            lines.append("")
    else:
        lines += [f"**Run:** {_safe_cell(report['run_id'])}; "
                  f"**records:** {report['record_count']}; "
                  f"**channels:** {len(report['per_channel'])}",
                  f"**Declared unit:** {_safe_cell(report['value_unit_declared'])}; "
                  f"**sampling rate:** {report['sample_rate_hz_declared']} Hz; "
                  "**time zone:** unknown",
                  f"**File checksums rechecked:** {report['verification']['file_hashes_rechecked']}",
                  f"**Quality flags:** {_safe_cell(report['verification']['issues_by_code'])}",
                  "", "## Per-channel summary", ""]
        for group_id, group in report["per_channel"].items():
            lines += [f"### {_safe_cell(group_id)}", "",
                      f"Bearing mapping: {_safe_cell(group['bearing_id'])}", "",
                      "Metric | Count | Missing | Mean | Median | P05 | P95",
                      "--- | ---: | ---: | ---: | ---: | ---: | ---:"]
            for key, summary in group["features"].items():
                lines.append(f"{_safe_cell(key)} | {summary['count']} | "
                             f"{summary['missing_count']} | {summary['mean']} | "
                             f"{summary['median']} | {summary['p05']} | {summary['p95']}")
            lines += ["", "Local timestamp (unknown time zone) | Native RMS",
                      "--- | ---:"]
            for point in group["trend_sample_first_last"]:
                lines.append(f"{_safe_cell(point['timestamp_local'])} | {point['rms_native']}")
            lines.append("")
    lines += ["**Limitations:** Descriptive exploratory statistics only. No trained "
              "predictive maintenance model, calibrated anomaly score, fault onset or RUL. "
              "Do not publish IMS-derived reports while rights remain unresolved.", ""]
    return "\n".join(lines)


def save_report(path: str | Path, report: dict, *, output_format: str = "json") -> None:
    """Write local JSON/Markdown exclusively to a new file."""
    if output_format not in ("json", "markdown"):
        raise ValueError("format must be json or markdown")
    if output_format == "json":
        write_local_manifest(path, report)
        return
    target = Path(path)
    if not target.parent.is_dir():
        raise ValueError(f"output parent directory missing: {target.parent}")
    payload = render_markdown(report)
    created = False
    try:
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write(payload)
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce descriptive synthetic or local IMS exploratory reports (no downloads)")
    parser.add_argument("--source", required=True, choices=("synthetic", "ims"))
    parser.add_argument("--input", type=Path, required=True,
                        help="synthetic export folder or local IMS inspection JSON")
    parser.add_argument("--out", type=Path, required=True, help="new local report path; never overwrite")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--verify-files", action="store_true",
                        help="for IMS: recheck hashes of local raw ASCII files")
    parser.add_argument("--expected-interval-s", type=float,
                        help="for IMS: review acquisition cadence")
    args = parser.parse_args()
    try:
        if args.source == "synthetic":
            if args.verify_files or args.expected_interval_s is not None:
                raise ValueError("IMS-only verification flags cannot be used with synthetic source")
            result = synthetic_quality_report(args.input)
        else:
            ims = _read_strict_json(args.input, MAX_REPORT_BYTES)
            result = ims_quality_report(ims, verify_files=args.verify_files,
                                        expected_interval_s=args.expected_interval_s)
        save_report(args.out, result, output_format=args.format)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Exploratory {args.source} report written locally: {args.out}")


if __name__ == "__main__":
    main()
