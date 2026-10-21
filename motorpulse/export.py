"""Bounded reproducible synthetic CSV/JSONL export (MP-008).

No third-party runtime dependencies, network access, or hardware integration.
Files contain simulated data, never validated machine diagnoses.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from .config_file import load_config_file
from .scenarios import AssetScenario, DEFAULT_ASSETS, configuration_dict
from .schema import SCHEMA_VERSION, SAMPLE_COUNT, SAMPLE_RATE_HZ, validate_snapshot
from .sim import DEFAULT_START_TIME_UTC, MotorSimulator, parse_start_time_utc

MAX_EXPORT_TICKS = 1000
MAX_DATA_BYTES = 64 * 1024 * 1024
EXPORT_FORMATS = ("csv", "jsonl", "both")
EXPORT_FIELDS = (
    "export_id",
    "schema_version",
    "tick",
    "recorded_at_utc",
    "event_id",
    "asset_id",
    "name",
    "scenario",
    "severity",
    "source",
    "timestamp_utc",
    "sample_rate_hz",
    "sample_count",
    "window_duration_s",
    "shaft_frequency_hz",
    "units",
    "rpm",
    "temperature_c",
    "load_factor",
    "sensor_quality",
    "sensor_quality_reasons",
    "sensor_drift_g",
    "rms_g",
    "peak_to_peak_g",
    "crest_factor",
    "spectral_window",
    "spectral_bin_hz",
    "dominant_frequency_hz",
    "shaft_1x_amplitude_g",
    "shaft_2x_amplitude_g",
    "band_80_400_rms_g",
    "health",
    "reasons",
    "rolling_window_ticks",
    "rolling_observations",
    "rolling_valid_observations",
    "rolling_rms_mean_g",
    "rolling_temperature_mean_c",
    "configured_scenario",
    "configured_severity",
    "onset_tick",
    "duration_ticks",
    "progression",
    "start_severity",
    "ramp_ticks",
    "ramp_fraction",
    "fault_phase",
    "operating_config",
)
NESTED_FIELDS = frozenset(
    ("units", "reasons", "sensor_quality_reasons", "operating_config")
)
# Hash the simulator and its generating dependencies, not just a fixed
# development-package version which can span many source revisions.
SOURCE_FILES = (
    "export.py",
    "sim.py",
    "scenarios.py",
    "signals.py",
    "spectral.py",
    "schema.py",
    "config_file.py",
)


def _canonical_source_bytes(data: bytes) -> bytes:
    """Normalize text-file line endings before provenance hashing."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _model_source_sha256() -> str:
    directory = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for filename in SOURCE_FILES:
        h.update(filename.encode("utf-8") + b"\0")
        h.update(_canonical_source_bytes((directory / filename).read_bytes()))
    return h.hexdigest()


def _canonical_json(value: Any) -> str:
    """Stable UTF-8 JSON, with no NaN or nonstandard numeric tokens."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _HashedWriter:
    """Accept CSV/JSONL strings, enforce a byte limit, and hash exact bytes."""

    def __init__(self, binary_file: Any):
        self.binary_file = binary_file
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, text: str) -> int:
        encoded = text.encode("utf-8")
        if self.size + len(encoded) > MAX_DATA_BYTES:
            raise ValueError(f"dataset file exceeds the {MAX_DATA_BYTES}-byte limit")
        self.binary_file.write(encoded)
        self.size += len(encoded)
        self.digest.update(encoded)
        return len(text)

    def summary(self) -> dict[str, int | str]:
        return {"bytes": self.size, "sha256": self.digest.hexdigest()}


def _csv_cell(key: str, value: Any) -> Any:
    if value is None:
        return ""  # Lossy NULL representation; see DATASET.md.
    if key in NESTED_FIELDS:
        return _canonical_json(value)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        # Names are user controlled. Prevent formula execution if opened in
        # spreadsheet software. JSONL keeps the unaltered source value.
        return "'" + value
    return value


def export_dataset(
    output_dir: str | Path,
    *,
    ticks: int,
    file_format: str = "both",
    seed: int = 42,
    assets: tuple[AssetScenario, ...] = DEFAULT_ASSETS,
    start_time_utc: datetime = DEFAULT_START_TIME_UTC,
    step_seconds: float = 1.5,
) -> dict[str, Any]:
    """Write one bounded run to a **new** directory, without overwriting.

    CSV and JSONL are per-asset **feature events**, not raw waveform files.
    Payload bytes / export_id reproduce for identical inputs; manifest
    generated_at_utc is actual wall clock and therefore varies.
    """
    if type(ticks) is not int or not 1 <= ticks <= MAX_EXPORT_TICKS:
        raise ValueError(f"ticks must be an integer in [1, {MAX_EXPORT_TICKS}]")
    if file_format not in EXPORT_FORMATS:
        raise ValueError("format must be csv, jsonl or both")
    sim = MotorSimulator(
        seed=seed,
        assets=assets,
        start_time_utc=start_time_utc,
        step_seconds=step_seconds,
    )
    last_time = sim.timestamp_for_tick(ticks)  # Check clock overflow before writing.
    config = configuration_dict(sim.assets)
    config_sha = _sha256(_canonical_json(config).encode("utf-8"))
    model_source_sha = _model_source_sha256()
    identity = {
        "config_sha256": config_sha,
        "model_source_sha256": model_source_sha,
        "seed": sim.seed,
        "start_time_utc": sim.start_time_utc.isoformat(),
        "step_seconds": sim.step_seconds,
        "ticks": ticks,
        "schema_version": SCHEMA_VERSION,
    }
    export_id = "sim-" + _sha256(_canonical_json(identity).encode("utf-8"))[:24]
    target = Path(output_dir)
    # mkdir(exist_ok=False) atomically claims the directory; no file replacement.
    # Do not implicitly make its parent or remove any pre-existing path.
    if not target.parent.is_dir():
        raise ValueError(f"parent directory does not exist: {target.parent}")
    target.mkdir(exist_ok=False)
    try:
        filenames = (
            ["events.csv"]
            if file_format == "csv"
            else ["events.jsonl"]
            if file_format == "jsonl"
            else ["events.csv", "events.jsonl"]
        )
        with ExitStack() as stack:
            sinks = {}
            for filename in filenames:
                f = stack.enter_context((target / filename).open("xb"))
                sinks[filename] = _HashedWriter(f)
            csv_writer = None
            if "events.csv" in sinks:
                csv_writer = csv.writer(sinks["events.csv"], lineterminator="\n")
                csv_writer.writerow(EXPORT_FIELDS)

            num_records = 0
            for tick in range(1, ticks + 1):
                snapshot = sim.step()
                validate_snapshot(snapshot)
                for asset in snapshot["assets"]:
                    payload = {
                        "export_id": export_id,
                        "schema_version": snapshot["schema_version"],
                        "tick": snapshot["tick"],
                        "recorded_at_utc": snapshot["recorded_at_utc"],
                        **asset,
                    }
                    if set(payload) != set(EXPORT_FIELDS):
                        raise ValueError(
                            "telemetry fields changed: update EXPORT_FIELDS and dictionary"
                        )
                    event = {k: payload[k] for k in EXPORT_FIELDS}
                    if csv_writer is not None:
                        csv_writer.writerow(
                            [_csv_cell(k, event[k]) for k in EXPORT_FIELDS]
                        )
                    if "events.jsonl" in sinks:
                        sinks["events.jsonl"].write(_canonical_json(event) + "\n")
                    num_records += 1
        manifest = {
            "manifest_version": "1.0.0",
            "dataset_type": "synthetic_motor_feature_events",
            "synthetic_only": True,
            "export_id": export_id,
            "schema_version": SCHEMA_VERSION,
            "package_version": "0.1.0.dev0",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "virtual_start_utc": sim.start_time_utc.isoformat(),
            "virtual_end_utc": last_time,
            "step_seconds": sim.step_seconds,
            "seed": sim.seed,
            "ticks": ticks,
            "assets": len(sim.assets),
            "events": num_records,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "sample_count": SAMPLE_COUNT,
            "format": file_format,
            "config_sha256": config_sha,
            "model_source_sha256": model_source_sha,
            "source_filenames": list(SOURCE_FILES),
            "configuration": config,
            "columns": list(EXPORT_FIELDS),
            "files": {filename: sinks[filename].summary() for filename in filenames},
            "label_semantics": {
                "scenario": "synthetic effective motor-fault truth, not a diagnosis",
                "configured_scenario": "synthetic scheduled motor-fault truth",
                "sensor_quality": "injected sensor-quality condition, not detected from real data",
                "health": "uncalibrated heuristic / unavailable / suspect, not a failure probability",
            },
        }
        with (target / "manifest.json").open(
            "x", encoding="utf-8", newline="\n"
        ) as output:
            output.write(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            )
        return manifest
    except BaseException:
        # This path was created by this call; leave no misleading partial export.
        shutil.rmtree(target)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export reproducible SYNTHETIC motor feature records; not field data"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="new output directory; existing paths are never overwritten",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        required=True,
        help=f"number of virtual ticks, 1–{MAX_EXPORT_TICKS}",
    )
    parser.add_argument("--format", choices=EXPORT_FORMATS, default="both")
    parser.add_argument(
        "--config",
        type=Path,
        help="optional validated local JSON motor scenario config",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--start-time-utc", type=parse_start_time_utc, default=DEFAULT_START_TIME_UTC
    )
    parser.add_argument("--step-seconds", type=float, default=1.5)
    args = parser.parse_args()
    try:
        assets = (
            load_config_file(args.config) if args.config is not None else DEFAULT_ASSETS
        )
        result = export_dataset(
            args.out_dir,
            ticks=args.ticks,
            file_format=args.format,
            seed=args.seed,
            assets=assets,
            start_time_utc=args.start_time_utc,
            step_seconds=args.step_seconds,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"Exported {result['events']} synthetic events to {args.out_dir} "
        f"(export_id={result['export_id']})"
    )


if __name__ == "__main__":
    main()
