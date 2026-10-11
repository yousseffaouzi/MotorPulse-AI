"""Conservative local-only IMS-style bearing snapshot ingestion (MP-009).

Reads timestamp-named whitespace-separated ASCII files one row at a time.
No network calls, downloads, archive extraction, inferred failure labels,
calibrated units, trained predictions, or third-party runtime packages.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from math import isfinite, sqrt
import os
from pathlib import Path
import re
from typing import Any

SOURCE_CARD_ID = "nasa-pcoe-ims-bearings"
TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}(\.[0-9]{2}){5}$")
SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
MAX_FILES = 100
MAX_DIRECTORY_ENTRIES = 20_000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 2048
MAX_SAMPLES = 32768
MAX_CHANNELS = 16
ALLOWED_UNITS = ("unknown", "g", "m/s^2", "V")


def _positive_int(value: object, name: str, limit: int) -> int:
    if type(value) is not int or not 1 <= value <= limit:
        raise ValueError(f"{name} must be an integer in [1, {limit}]")
    return value


def _read_strict_json(path: str | Path, max_bytes: int = 16384) -> object:
    p = Path(path)
    try:
        with p.open("rb") as handle:
            data = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ValueError(f"cannot read JSON file {p}: {exc}") from exc
    if not data or len(data) > max_bytes:
        raise ValueError(f"JSON file must be 1-{max_bytes} bytes: {p}")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict:
        row: dict = {}
        for key, value in pairs:
            if key in row:
                raise ValueError(f"duplicate JSON key {key!r}")
            row[key] = value
        return row

    def nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value} is forbidden")

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=object_pairs,
                          parse_constant=nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid UTF-8 JSON in {p}: {exc}") from exc


def load_channel_map(path: str | Path, test_set: str, channel_count: int) -> dict:
    """Use only an explicitly supplied bearing mapping, with a source note."""
    document = _read_strict_json(path)
    if not isinstance(document, dict) or set(document) != {
        "test_set", "channels", "source_note",
    }:
        raise ValueError("channel map needs exactly test_set, channels, source_note")
    if document["test_set"] != test_set:
        raise ValueError("channel-map test_set does not match requested test set")
    mapping = document["channels"]
    if not isinstance(mapping, dict) or set(mapping) != {
        str(i) for i in range(1, channel_count + 1)
    }:
        raise ValueError("channel map must cover exactly the requested 1-based channels")
    if not isinstance(document["source_note"], str) or not (
        1 <= len(document["source_note"].strip()) <= 256
    ):
        raise ValueError("source_note must explain the mapping (1-256 characters)")
    for channel, bearing in mapping.items():
        if not isinstance(bearing, str) or not re.fullmatch(
            r"bearing-[1-9][0-9]{0,2}", bearing
        ):
            raise ValueError(f"invalid explicit bearing ID for channel {channel}")
    return document


def _local_timestamp(name: str) -> datetime:
    if not TIMESTAMP_PATTERN.fullmatch(name):
        raise ValueError(f"not an IMS timestamp filename: {name}")
    try:
        return datetime.strptime(name, "%Y.%m.%d.%H.%M.%S")
    except ValueError as exc:
        raise ValueError(f"invalid calendar timestamp in filename: {name}") from exc


def _list_files(directory: Path, limit: int) -> list[tuple[datetime, Path]]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"input directory must exist and not be a symlink: {directory}")
    files: list[tuple[datetime, Path]] = []
    seen = 0
    with os.scandir(directory) as listing:
        for item in listing:
            seen += 1
            if seen > MAX_DIRECTORY_ENTRIES:
                raise ValueError("too many directory entries")
            if not TIMESTAMP_PATTERN.fullmatch(item.name):
                continue  # Other documentation and manifests are not measurements.
            timestamp = _local_timestamp(item.name)
            if item.is_symlink() or not item.is_file(follow_symlinks=False):
                raise ValueError(f"timestamp entry must be a regular file: {item.name}")
            files.append((timestamp, Path(item.path)))
    files.sort(key=lambda item: item[0])
    if not files:
        raise ValueError("no timestamp-named IMS-style records found in directory")
    # The earliest files are selected chronologically, not by filesystem order.
    return files[:limit]


def _read_record(path: Path, *, samples: int, channels: int,
                 unit: str) -> dict[str, Any]:
    stat = path.stat(follow_symlinks=False)
    if not 0 < stat.st_size <= MAX_FILE_BYTES:
        raise ValueError(f"{path.name}: file size must be 1-{MAX_FILE_BYTES} bytes")
    digest = hashlib.sha256()
    squares = [0.0] * channels
    lows = [float("inf")] * channels
    highs = [float("-inf")] * channels
    peak = [0.0] * channels
    rows = 0
    counted_bytes = 0
    with path.open("rb") as handle:
        while True:
            line = handle.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            counted_bytes += len(line)
            if counted_bytes > MAX_FILE_BYTES:
                raise ValueError(f"{path.name}: data exceeds {MAX_FILE_BYTES} bytes")
            if len(line) > MAX_LINE_BYTES:
                raise ValueError(f"{path.name}:{rows+1}: line too long")
            digest.update(line)
            rows += 1
            if rows > samples:
                raise ValueError(f"{path.name}: more than expected {samples} rows")
            try:
                values = line.decode("ascii").split()
            except UnicodeDecodeError as exc:
                raise ValueError(f"{path.name}:{rows}: non-ASCII raw data") from exc
            if len(values) != channels:
                raise ValueError(f"{path.name}:{rows}: expected {channels} columns, got {len(values)}")
            for index, token in enumerate(values):
                try:
                    reading = float(token)
                except ValueError as exc:
                    raise ValueError(f"{path.name}:{rows}: nonnumeric channel {index+1}") from exc
                if not isfinite(reading):
                    raise ValueError(f"{path.name}:{rows}: nonfinite channel {index+1}")
                squares[index] += reading * reading
                if not isfinite(squares[index]):
                    raise ValueError(f"{path.name}:{rows}: numeric overflow")
                lows[index] = min(lows[index], reading)
                highs[index] = max(highs[index], reading)
                peak[index] = max(peak[index], abs(reading))
    if rows != samples:
        raise ValueError(f"{path.name}: expected exactly {samples} rows, got {rows}")
    return {
        "bytes": counted_bytes,
        "sha256": digest.hexdigest(),
        "sample_count": rows,
        "channels": [
            {
                "channel_id": f"ch-{index+1:02d}",
                "rms_native": sqrt(squares[index] / rows),
                "peak_to_peak_native": highs[index] - lows[index],
                "crest_factor": (peak[index] / sqrt(squares[index] / rows)
                                 if squares[index] else 0.0),
                "value_unit": unit,
            }
            for index in range(channels)
        ],
    }


def inspect_ims_directory(
    input_dir: str | Path, *,
    test_set: str,
    sample_rate_hz: float,
    expected_samples: int,
    expected_channels: int,
    max_files: int = 10,
    value_unit: str = "unknown",
    channel_map: dict | None = None,
    archive_sha256: str | None = None,
    acquired_on: str | None = None,
) -> dict[str, Any]:
    """Inspect user-provided records without producing a public dataset.

    Physical bearings are null unless a documented manual channel mapping is
    explicitly supplied. Timestamps in filenames have an *unknown* timezone.
    """
    if test_set not in ("1", "2", "3"):
        raise ValueError("test_set must be '1', '2' or '3'")
    _positive_int(expected_samples, "expected_samples", MAX_SAMPLES)
    _positive_int(expected_channels, "expected_channels", MAX_CHANNELS)
    _positive_int(max_files, "max_files", MAX_FILES)
    if (type(sample_rate_hz) not in (int, float) or
            not isfinite(sample_rate_hz) or not 1 <= sample_rate_hz <= 1_000_000):
        raise ValueError("sample_rate_hz must be finite and in [1, 1000000]")
    if value_unit not in ALLOWED_UNITS:
        raise ValueError("value_unit must be 'unknown', 'g', 'm/s^2', or 'V'")
    if archive_sha256 is not None and not (
        isinstance(archive_sha256, str) and SHA256_PATTERN.fullmatch(archive_sha256)
    ):
        raise ValueError("archive_sha256 must be 64 hex characters or omitted")
    if acquired_on is not None:
        if type(acquired_on) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", acquired_on):
            raise ValueError("acquired_on must be ISO date YYYY-MM-DD")
        try:
            date.fromisoformat(acquired_on)
        except ValueError as exc:
            raise ValueError("acquired_on is not a real date") from exc
    if channel_map is not None:
        if (not isinstance(channel_map, dict) or
                channel_map.get("test_set") != test_set or
                not isinstance(channel_map.get("channels"), dict) or
                set(channel_map["channels"]) != {
                    str(i) for i in range(1, expected_channels + 1)
                } or
                not isinstance(channel_map.get("source_note"), str) or
                not channel_map["source_note"].strip()):
            raise ValueError("channel map is incomplete or mismatches requested test set")
        if any(not isinstance(v, str) or not re.fullmatch(
            r"bearing-[1-9][0-9]{0,2}", v
        ) for v in channel_map["channels"].values()):
            raise ValueError("invalid channel map bearing labels")
    directory = Path(input_dir)
    selected = _list_files(directory, max_files)
    rows: list[dict[str, Any]] = []
    for timestamp, path in selected:
        record = _read_record(path, samples=expected_samples,
                              channels=expected_channels, unit=value_unit)
        for index, feature in enumerate(record["channels"], start=1):
            feature["bearing_id"] = (channel_map["channels"][str(index)]
                                     if channel_map is not None else None)
            feature["group_key"] = f"ims:set-{test_set}:ch-{index:02d}"
        rows.append({
            "filename": path.name,
            "timestamp_local": timestamp.isoformat(),
            "timezone": "unknown; no UTC conversion",
            "test_set": test_set,
            "run_id": f"ims-set-{test_set}",
            **record,
        })
    return {
        "schema_version": "1.0.0",
        "source_card_id": SOURCE_CARD_ID,
        "data_source": "user_supplied_local_ims_style",
        "publication_status": "local_only_do_not_redistribute",
        "input_directory": str(directory.resolve()),
        "test_set": test_set,
        "run_id": f"ims-set-{test_set}",
        "original_archive_sha256": archive_sha256.lower() if archive_sha256 else None,
        "acquired_on": acquired_on,
        "sample_rate_hz_declared": float(sample_rate_hz),
        "samples_per_record_declared": expected_samples,
        "channels_per_record_declared": expected_channels,
        "snapshot_duration_s": expected_samples / sample_rate_hz,
        "value_unit_declared": value_unit,
        "channel_mapping": channel_map,
        "timestamp_timezone": "unknown",
        "record_count": len(rows),
        "channel_record_count": len(rows) * expected_channels,
        "records": rows,
        "ground_truth": {
            "window_fault_label": None,
            "fault_onset_time": None,
            "rul_seconds": None,
            "note": "IMS test end failures are not per-window labels; none inferred here.",
        },
    }


def write_local_manifest(path: str | Path, report: dict[str, Any]) -> None:
    """Create a new local JSON report without overwriting an existing file."""
    target = Path(path)
    if not target.parent.is_dir():
        raise ValueError(f"manifest parent directory missing: {target.parent}")
    payload = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False,
                         allow_nan=False) + "\n"
    created = False
    try:
        with target.open("x", encoding="utf-8", newline="\n") as out:
            created = True
            out.write(payload)
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect locally supplied IMS-style ASCII files; never download or publish raw data")
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="directory containing timestamp-named ASCII files (not ZIP/RAR)")
    parser.add_argument("--test-set", choices=("1", "2", "3"), required=True)
    parser.add_argument("--sample-rate-hz", type=float, required=True,
                        help="rate asserted from your local source notes (not inferred)")
    parser.add_argument("--expected-samples", type=int, required=True)
    parser.add_argument("--expected-channels", type=int, required=True)
    parser.add_argument("--max-files", type=int, default=10)
    parser.add_argument("--value-unit", choices=ALLOWED_UNITS, default="unknown")
    parser.add_argument("--channel-map", type=Path,
                        help="optional user-verified JSON channel-to-bearing map")
    parser.add_argument("--archive-sha256", help="optional measured SHA-256 of the source archive")
    parser.add_argument("--acquired-on", help="optional archive acquisition date YYYY-MM-DD")
    parser.add_argument("--manifest", type=Path,
                        help="optional new local report JSON; do not commit third-party-derived results")
    args = parser.parse_args()
    try:
        mapping = (load_channel_map(args.channel_map, args.test_set,
                                    args.expected_channels)
                   if args.channel_map else None)
        report = inspect_ims_directory(
            args.input_dir, test_set=args.test_set,
            sample_rate_hz=args.sample_rate_hz,
            expected_samples=args.expected_samples,
            expected_channels=args.expected_channels,
            max_files=args.max_files, value_unit=args.value_unit,
            channel_map=mapping, archive_sha256=args.archive_sha256,
            acquired_on=args.acquired_on)
        if args.manifest is not None:
            write_local_manifest(args.manifest, report)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Validated {report['record_count']} IMS-style snapshots / "
          f"{report['channel_record_count']} channel summaries "
          f"(test set {args.test_set}; declared fs={args.sample_rate_hz:g} Hz).")
    if args.manifest:
        print(f"Local-only report: {args.manifest}")


if __name__ == "__main__":
    main()
