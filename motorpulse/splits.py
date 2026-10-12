"""MP-030: deterministic leakage-aware offline split planning.

No training, data copying, downloads, or real-data redistribution. Split source
identities before fitting scalers or evaluating any model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from math import ceil, isfinite
from pathlib import Path
from typing import Any, Sequence

from .eda import synthetic_quality_report
from .ims import _read_strict_json, write_local_manifest
from .ims_validation import MAX_REPORT_BYTES, validate_ims_report

MAX_SOURCES = 100
PARTITIONS = ("train", "validation", "test")
DEFAULT_RATIOS = (0.6, 0.2, 0.2)
MIN_PURGE_TICKS = 4   # 5-tick rolling RMS includes four previous windows.


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _ratios(value: Sequence[float]) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("ratios must be train, validation, test")
    if any(type(v) not in (float, int) or not isfinite(v) or v <= 0 for v in value):
        raise ValueError("ratios must be positive finite numbers")
    if abs(sum(value) - 1) > 1e-9:
        raise ValueError("split ratios must sum to one")
    return tuple(float(v) for v in value)


def _allocate(count: int, ratios: Sequence[float]) -> tuple[int, int, int]:
    if type(count) is not int or count < 3:
        raise ValueError("at least three independent groups/windows are required")
    values = _ratios(ratios)
    exact = [count * portion for portion in values]
    # Each of the three sets needs at least one independent run/window.
    # Assign any remaining groups to the largest target-count deficit.
    allocated = [1, 1, 1]
    for _ in range(count - 3):
        candidate = max(range(3), key=lambda k: (exact[k] - allocated[k], -k))
        allocated[candidate] += 1
    return tuple(allocated)


def _source(path: str | Path, kind: str) -> dict:
    """Validate a complete local source and derive a path-independent identity."""
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("source manifest must be an existing, non-symlink file")
    if kind == "synthetic":
        if p.name != "manifest.json":
            raise ValueError("synthetic input must be a manifest.json in an export directory")
        summary = synthetic_quality_report(p.parent)
        manifest = _read_strict_json(p, 128 * 1024)
        for field in ("seed", "step_seconds", "virtual_start_utc",
                      "config_sha256", "model_source_sha256"):
            if field not in manifest:
                raise ValueError(f"missing source provenance field: {field}")
        if type(manifest["seed"]) is not int or type(manifest["step_seconds"]) not in (int,float):
            raise ValueError("invalid synthetic seed / virtual step")
        if not isfinite(manifest["step_seconds"]) or manifest["step_seconds"] <= 0:
            raise ValueError("invalid synthetic virtual step")
        for key in ("config_sha256", "model_source_sha256"):
            val = manifest[key]
            if type(val) is not str or len(val) != 64 or any(c not in "0123456789abcdef" for c in val):
                raise ValueError(f"invalid provenance hash: {key}")
        group_id = "synthetic-run:" + _hash({
            "seed": manifest["seed"], "config_sha256": manifest["config_sha256"],
            "model_source_sha256": manifest["model_source_sha256"],
            "virtual_start_utc": manifest["virtual_start_utc"],
            "step_seconds": manifest["step_seconds"],
        })[:24]
        return {
            "source_type": "synthetic_motor_feature_events",
            "source_id": summary["export_id"],
            "group_id": group_id,
            "source_data_sha256": summary["source_file_sha256"],
            "records": summary["events"],
            "ticks": summary["ticks"],
            "assets": summary["assets"],
            "virtual_start_utc": manifest["virtual_start_utc"],
            "step_seconds": manifest["step_seconds"],
            "window_duration_s": manifest["sample_count"] / manifest["sample_rate_hz"],
            "model_source_sha256": manifest["model_source_sha256"],
            "config_sha256": manifest["config_sha256"],
            "publication_status": "synthetic_demo",
        }
    if kind == "ims":
        document = _read_strict_json(p, MAX_REPORT_BYTES)
        validation = validate_ims_report(document, verify_files=False)
        # The entire IMS test-set/run is held out together; a per-channel or
        # per-bearing split would risk same-rig and adjacent-time leakage.
        run_id = validation["run_id"]
        digest = _hash({
            "source_card_id": document["source_card_id"],
            "run_id": run_id,
            "records": [(rec["filename"], rec["sha256"], rec["bytes"])
                        for rec in document["records"]],
            "sampling": (document["sample_rate_hz_declared"],
                         document["samples_per_record_declared"],
                         document["value_unit_declared"]),
        })
        return {
            "source_type": "user_supplied_local_ims_style",
            "source_id": f"ims:{run_id}:{digest[:24]}",
            "group_id": "ims-run:" + run_id,
            "source_data_sha256": digest,
            "record_hashes": sorted(rec["sha256"] for rec in document["records"]),
            "records": document["channel_record_count"],
            "snapshots": document["record_count"],
            "channels": document["channels_per_record_declared"],
            "sample_rate_hz_declared": document["sample_rate_hz_declared"],
            "value_unit_declared": document["value_unit_declared"],
            "timestamp_timezone": "unknown",
            "bearing_mapping_verified": False,
            "window_fault_labels": None,
            "quality_issues": validation["counts_by_issue"],
            "publication_status": "local_only_do_not_redistribute",
        }
    raise ValueError("source type must be synthetic or ims")


def group_split(source_paths: Sequence[str | Path], *,
                source_type: str, seed: int = 42,
                ratios: Sequence[float] = DEFAULT_RATIOS) -> dict:
    """Partition distinct complete source runs; preserve grouped source identity."""
    _ratios(ratios)
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("split seed must be an integer in [0, 2^32-1]")
    if not isinstance(source_paths, (tuple, list)) or not 3 <= len(source_paths) <= MAX_SOURCES:
        raise ValueError(f"need 3–{MAX_SOURCES} complete source runs")
    if source_type not in ("synthetic", "ims"):
        raise ValueError("source_type must be synthetic or ims")
    entries = [_source(path, source_type) for path in source_paths]
    groups = [entry["group_id"] for entry in entries]
    if len(set(groups)) != len(groups):
        raise ValueError("duplicate/overlapping run group (same source run in multiple inputs)")
    source_ids = [entry["source_id"] for entry in entries]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("duplicate source export/run identity")
    if source_type == "ims":
        # Exact waveform files must not appear in multiple nominal runs.
        all_hashes = [hash for entry in entries for hash in entry["record_hashes"]]
        if len(set(all_hashes)) != len(all_hashes):
            raise ValueError("identical raw-record SHA-256 reused across IMS run groups")
    amounts = _allocate(len(entries), ratios)
    ordered = sorted(entries, key=lambda x: (
        hashlib.sha256(f"{seed}:{x['group_id']}".encode()).hexdigest(),
        x["group_id"],
    ))
    partitions = {}
    start = 0
    for name, amount in zip(PARTITIONS, amounts):
        selected = ordered[start:start + amount]
        partitions[name] = {
            "group_ids": sorted(x["group_id"] for x in selected),
            "source_ids": sorted(x["source_id"] for x in selected),
            "groups": amount, "records": sum(x["records"] for x in selected),
        }
        start += amount
    public_sources = [{k:v for k,v in entry.items() if k != "record_hashes"}
                      for entry in sorted(entries, key=lambda x:x["group_id"])]
    manifest = {
        "split_version": "1.0.0", "policy": "whole_run_grouped",
        "source_type": entries[0]["source_type"], "seed": seed,
        "ratios": list(_ratios(ratios)),
        "group_boundary": "complete synthetic generator run"
                          if source_type == "synthetic"
                          else "complete IMS test set / rig run (all related channels and timestamps)",
        "partitions": partitions, "sources": public_sources,
        "counts_note": "ratios allocate counts of independent run groups, not individual event rows",
        "preprocessing_rule": "fit transforms/feature selection/thresholds on training groups only",
        "label_blind_assignment": True,
        "label_policy": "synthetic scripted fault labels only; no IMS per-window fault truth"
                        if source_type == "synthetic" else
                        "IMS per-window failure onset and RUL unknown, labels unavailable",
        "publication_status": "synthetic_demo" if source_type == "synthetic"
                              else "local_only_do_not_redistribute",
    }
    manifest["plan_sha256"] = _hash(manifest)
    return manifest


def chronological_split(source_manifest: str | Path, *,
                        ratios: Sequence[float] = DEFAULT_RATIOS,
                        purge_ticks: int = MIN_PURGE_TICKS) -> dict:
    """Explicitly exploratory within-run time holdout, not independent-run test.

    A 5-tick feature history needs >=4 discarded ticks on each boundary.
    Extra purge is required when waveform windows nominally overlap.
    """
    ratios = _ratios(ratios)
    entry = _source(source_manifest, "synthetic")
    if type(purge_ticks) is not int or purge_ticks < MIN_PURGE_TICKS:
        raise ValueError("purge_ticks must be >=4 for five-tick rolling features")
    min_gap = max(MIN_PURGE_TICKS,
                  ceil(entry["window_duration_s"] / entry["step_seconds"]))
    if purge_ticks < min_gap:
        raise ValueError(f"purge_ticks must be >= {min_gap} for overlapping windows")
    remaining = entry["ticks"] - 2 * purge_ticks
    amounts = _allocate(remaining, ratios)
    train, val, test = amounts
    partitions = {
        "train": {"tick_start": 1, "tick_end": train,
                  "ticks": train, "records": train * entry["assets"]},
        "validation": {"tick_start": train+purge_ticks+1,
                       "tick_end": train+purge_ticks+val,
                       "ticks": val, "records": val * entry["assets"]},
        "test": {"tick_start": train+2*purge_ticks+val+1,
                 "tick_end": entry["ticks"],
                 "ticks": test, "records": test * entry["assets"]},
    }
    purged = [
        {"tick_start": train+1, "tick_end": train+purge_ticks},
        {"tick_start": train+purge_ticks+val+1,
         "tick_end": train+2*purge_ticks+val},
    ]
    result = {
        "split_version": "1.0.0", "policy": "synthetic_chronological_exploratory",
        "source_type": "synthetic_motor_feature_events",
        "source_id": entry["source_id"], "source_group_id": entry["group_id"],
        "source_data_sha256": entry["source_data_sha256"],
        "model_source_sha256": entry["model_source_sha256"],
        "ratios": list(ratios), "purge_ticks": purge_ticks,
        "minimum_purge_ticks": min_gap,
        "partitions": partitions, "purged_ranges": purged,
        "group_boundary": "entire asset tick across all motors; time ordered",
        "evaluation_warning": "same generator run across partitions; correlated conditions remain. NOT independent-run validation",
        "preprocessing_rule": "fit on train ticks only; do not use validation/test values or labels for tuning preprocessing",
        "label_blind_assignment": True,
        "publication_status": "synthetic_demo",
    }
    # An independently maintained feature contract rechecks inclusive tick
    # ranges, the 5-tick rolling lookback and physical waveform window width.
    # Chronological plans remain exploratory; MP-010 training rejects them.
    from .feature_pipeline import validate_chronological_boundaries
    validate_chronological_boundaries(
        result, window_duration_s=entry["window_duration_s"],
        step_seconds=entry["step_seconds"],
    )
    result["plan_sha256"] = _hash(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan leakage-aware offline splits; no training or original-data publication")
    parser.add_argument("--source", choices=("synthetic", "ims"), required=True)
    parser.add_argument("--input", type=Path, nargs="+", required=True,
                        help="synthetic manifest.json paths, or local IMS inspection JSON reports")
    parser.add_argument("--out", type=Path, required=True,
                        help="new local split-plan JSON; existing outputs never overwritten")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=.6)
    parser.add_argument("--validation-ratio", type=float, default=.2)
    parser.add_argument("--test-ratio", type=float, default=.2)
    parser.add_argument("--chronological", action="store_true",
                        help="single synthetic run only; NOT independent-run validation")
    parser.add_argument("--purge-ticks", type=int, default=MIN_PURGE_TICKS)
    args = parser.parse_args()
    try:
        ratios = (args.train_ratio, args.validation_ratio, args.test_ratio)
        if args.chronological:
            if args.source != "synthetic" or len(args.input) != 1:
                raise ValueError("chronological mode requires exactly one synthetic manifest")
            result = chronological_split(args.input[0], ratios=ratios,
                                         purge_ticks=args.purge_ticks)
        else:
            if args.purge_ticks != MIN_PURGE_TICKS:
                raise ValueError("--purge-ticks only applies to chronological mode")
            result = group_split(args.input, source_type=args.source,
                                 seed=args.seed, ratios=ratios)
        write_local_manifest(args.out, result)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(f"Split plan ({result['policy']}) created: {args.out} "
          f"[{result['plan_sha256'][:12]}]; no data moved or transformed.")


if __name__ == "__main__":
    main()
