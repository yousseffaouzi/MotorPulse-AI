"""Versioned offline dataset cards for synthetic runs and local IMS reports (MP-032).

Template JSON is bundled as package data, so installed commands work without
a repository checkout. No downloads, source-data uploads, or trained models.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .cwru import (
    MAX_REPORT_BYTES as MAX_CWRU_REPORT_BYTES,
    SOURCE_CARD_ID as CWRU_SOURCE_CARD_ID,
    validate_cwru_report,
)
from .eda import synthetic_quality_report
from .export import _canonical_json
from .ims import _read_strict_json, write_local_manifest
from .ims_validation import MAX_REPORT_BYTES, validate_ims_report

CARD_VERSION = "1.0.0"
TEMPLATE_FILENAMES = {
    "synthetic": "synthetic-v1.json",
    "ims": "ims-v1.json",
    "cwru": "cwru-v1.json",
}
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_CARD_KEYS = frozenset((
    "card_version", "card_id", "instance_kind", "run_provenance",
    "dataset_type", "title", "creator_or_provider", "distributor",
    "provenance_status", "citation", "license", "collection", "labels",
    "measurement_quality", "recommended_splits", "intended_uses",
    "excluded_uses", "known_limitations", "references",
    "publication_status", "rights_review",
))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any, name: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase 64-digit SHA-256")
    return value


def _present_text(value: Any, field: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field} must be nonempty text")


def _required_map(value: Any, name: str) -> Mapping:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name} must be a nonempty object")
    return value


def validate_card(card: Any) -> None:
    """Check published card contracts, including conservative rights assertions.

    This is a project-specific offline validator, not an external license audit.
    """
    if type(card) is not dict or set(card) != _CARD_KEYS:
        raise ValueError("card keys differ from v1 card contract")
    if card["card_version"] != CARD_VERSION or card["instance_kind"] not in ("template", "run"):
        raise ValueError("invalid card version or instance kind")
    for key in ("card_id", "title", "creator_or_provider", "distributor",
                "provenance_status", "citation", "recommended_splits",
                "publication_status"):
        _present_text(card[key], key)
    for field in ("intended_uses", "excluded_uses", "known_limitations"):
        value = card[field]
        if not isinstance(value, list) or len(value) < 2 or any(
            type(item) is not str or not item.strip() for item in value
        ):
            raise ValueError(f"{field} requires at least two nonempty text entries")
    for field in ("license", "collection", "labels", "measurement_quality",
                  "references", "rights_review"):
        _required_map(card[field], field)
    for key in ("code_license", "license_status", "original_or_derived_redistribution"):
        _present_text(card["license"].get(key), f"license.{key}")
    rights = card["rights_review"]
    if type(rights.get("raw_third_party_data_included")) is not bool or rights["raw_third_party_data_included"]:
        raise ValueError("bundled cards must not contain third-party raw data")
    run = card["run_provenance"]
    if card["instance_kind"] == "template":
        if run is not None:
            raise ValueError("template must not pretend to represent acquired records")
    elif not isinstance(run, dict) or not run:
        raise ValueError("run card needs actual source-linked provenance")
    kind = card["dataset_type"]
    if kind == "synthetic_motor_feature_events":
        if card["publication_status"] != "synthetic_demo" or rights.get("status") != "no_third_party_source_inputs":
            raise ValueError("invalid synthetic origin/publication policy")
        if card["license"].get("dataset_specific_license") is not None:
            raise ValueError("do not imply a separately assigned synthetic data license")
        if not (card["labels"].get("motor_fault") and card["labels"].get("sensor_quality")
                and card["labels"].get("health")):
            raise ValueError("synthetic labels must distinguish machine/sensor/rules")
        if any(card["labels"].get(x) is not None for x in ("failure_probability", "remaining_useful_life")):
            raise ValueError("do not invent synthetic prognostic labels")
        if run is not None:
            for name in ("model_source_sha256", "config_sha256", "events_jsonl_sha256"):
                _digest(run.get(name), name)
            if (not isinstance(run.get("export_id"), str) or
                    not run["export_id"].startswith("sim-")):
                raise ValueError("invalid synthetic export ID")
            for name in ("events", "ticks", "assets"):
                if type(run.get(name)) is not int or run[name] < 1:
                    raise ValueError(f"invalid synthetic run {name}")
            if type(run.get("seed")) is not int:
                raise ValueError("synthetic seed must be an integer")
    elif kind == "user_supplied_local_ims_style":
        if card["publication_status"] != "local_only_do_not_redistribute":
            raise ValueError("IMS-derived publication must remain local-only")
        if rights.get("status") != "hold" or rights.get("derived_publication_cleared") is not False:
            raise ValueError("IMS rights have not been cleared")
        if card["license"].get("license_status") != "other-license-specified":
            raise ValueError("IMS catalog license badge must not be reinterpreted")
        if card["license"].get("dataset_specific_license") is not None:
            raise ValueError("no verified standardized IMS source license")
        for key in ("motor_fault", "sensor_quality", "health", "failure_probability",
                    "remaining_useful_life", "window_fault_onset"):
            if card["labels"].get(key) is not None:
                raise ValueError(f"unverified IMS label must remain null: {key}")
        if card["collection"].get("sample_rate_hz") is not None:
            raise ValueError("global IMS sample rate has not been verified")
        if card["collection"].get("sample_count") is not None:
            raise ValueError("global IMS sample count has not been verified")
        if run is not None:
            _digest(run.get("inspection_report_sha256"), "inspection_report_sha256")
            if run.get("source_card_id") != "nasa-pcoe-ims-bearings":
                raise ValueError("IMS source card mismatch")
            if run.get("run_id") not in ("ims-set-1", "ims-set-2", "ims-set-3"):
                raise ValueError("unsupported IMS run provenance")
            if run.get("timestamp_timezone") != "unknown":
                raise ValueError("original IMS timezone is unverified")
            if run.get("window_fault_label") is not None or run.get("rul_seconds") is not None:
                raise ValueError("window truth / RUL unknown")
            if type(run.get("file_hashes_rechecked")) is not bool:
                raise ValueError("file re-verification status must be boolean")
    elif kind == "user_supplied_local_cwru_seeded_fault":
        if card["publication_status"] != "local_only_do_not_redistribute":
            raise ValueError("CWRU publication must remain local-only")
        if rights.get("status") != "hold" or rights.get("derived_publication_cleared") is not False:
            raise ValueError("CWRU redistribution rights have not been cleared")
        if card["license"].get("license_status") != "unverified":
            raise ValueError("CWRU source license must remain unverified")
        if card["license"].get("dataset_specific_license") is not None:
            raise ValueError("no verified standardized CWRU source license")
        for key in ("sensor_quality", "health", "failure_probability", "remaining_useful_life", "window_fault_onset"):
            if card["labels"].get(key) is not None:
                raise ValueError(f"unsupported CWRU label must remain null: {key}")
        if run is not None:
            _digest(run.get("inspection_report_sha256"), "inspection_report_sha256")
            _digest(run.get("source_file_sha256"), "source_file_sha256")
            if run.get("source_card_id") != CWRU_SOURCE_CARD_ID:
                raise ValueError("CWRU source card mismatch")
            if run.get("run_to_failure") is not False:
                raise ValueError("CWRU seeded-fault record is not run-to-failure")
            if run.get("failure_time") is not None or run.get("remaining_useful_life") is not None:
                raise ValueError("CWRU run card must not invent failure time or RUL")
            if run.get("rights_status") != "unverified_for_redistribution":
                raise ValueError("CWRU run card must preserve redistribution uncertainty")
            if run.get("fault_type") not in ("normal", "inner_race", "ball", "outer_race"):
                raise ValueError("invalid CWRU seeded fault type")
            if type(run.get("sample_count")) is not int or run["sample_count"] < 1:
                raise ValueError("invalid CWRU sample count")
    else:
        raise ValueError("unsupported dataset kind")


def template_card(kind: str) -> dict:
    if kind not in TEMPLATE_FILENAMES:
        raise ValueError("kind must be synthetic, ims or cwru")
    path = files("motorpulse").joinpath("cards", TEMPLATE_FILENAMES[kind])
    card = json.loads(path.read_text(encoding="utf-8"))
    validate_card(card)
    return card


def synthetic_run_card(export_dir: str | Path) -> dict:
    """Bind a versioned card to actual verified JSONL export provenance."""
    quality = synthetic_quality_report(export_dir)  # rehash files, validate events
    manifest = _read_strict_json(Path(export_dir) / "manifest.json", 128 * 1024)
    if type(manifest) is not dict or type(manifest.get("configuration")) is not dict:
        raise ValueError("missing expanded synthetic configuration")
    conf_sha = _sha(_canonical_json(manifest["configuration"]).encode("utf-8"))
    if conf_sha != manifest.get("config_sha256"):
        raise ValueError("synthetic configuration SHA-256 mismatch")
    model_hash = _digest(manifest.get("model_source_sha256"), "model source SHA-256")
    card = deepcopy(template_card("synthetic"))
    card["instance_kind"] = "run"
    card["card_id"] += ":" + quality["export_id"]
    card["run_provenance"] = {
        "export_id": quality["export_id"],
        "events_jsonl_sha256": quality["source_file_sha256"],
        "config_sha256": conf_sha, "model_source_sha256": model_hash,
        "events": quality["events"], "ticks": quality["ticks"],
        "assets": quality["assets"], "seed": manifest["seed"],
        "virtual_start_utc": quality["virtual_start_utc"],
        "virtual_end_utc": quality["virtual_end_utc"],
        "sample_rate_hz": quality["sample_rate_hz"],
        "sample_count": quality["sample_count"],
        "source_file_hashes": {
            filename: info["sha256"] for filename, info in sorted(manifest["files"].items())
        },
        "generated_at_utc": None,
        "generated_at_note": "The manifest creation wall clock is omitted so identical source data yield identical cards.",
    }
    validate_card(card)
    return card


def ims_run_card(inspection_json: str | Path, *, verify_files: bool = False) -> dict:
    """Generate *local-only* metadata without copying experimental samples."""
    source = _read_strict_json(inspection_json, MAX_REPORT_BYTES)
    quality = validate_ims_report(source, verify_files=verify_files)
    card = deepcopy(template_card("ims"))
    card["instance_kind"] = "run"
    # Hash canonical content rather than absolute report path; only derived
    # metadata is emitted, never samples, per-channel features or local paths.
    report_digest = _sha(_canonical_json(source).encode("utf-8"))
    card["card_id"] += ":" + quality["run_id"] + ":" + report_digest[:16]
    card["run_provenance"] = {
        "source_card_id": source["source_card_id"],
        "inspection_report_sha256": report_digest,
        "run_id": quality["run_id"], "test_set": source["test_set"],
        "snapshot_count": source["record_count"],
        "channel_record_count": source["channel_record_count"],
        "sample_rate_hz_declared_by_user": source["sample_rate_hz_declared"],
        "sample_count_declared_by_user": source["samples_per_record_declared"],
        "value_unit_declared_by_user": source["value_unit_declared"],
        "timestamp_timezone": "unknown",
        "original_archive_sha256_user_supplied": source["original_archive_sha256"],
        "acquired_on_user_supplied": source["acquired_on"],
        "file_hashes_rechecked": quality["verified_file_checksums"],
        "quality_flag_counts": quality["counts_by_issue"],
        "window_fault_label": None, "fault_onset_time": None, "rul_seconds": None,
        "source_archive_inspected_by_project": False,
        "rights_status": "unverified; no public derived-data release",
    }
    validate_card(card)
    return card


def cwru_run_card(inspection_json: str | Path) -> dict:
    """Generate local-only CWRU provenance without copying measurement summaries."""
    source = _read_strict_json(inspection_json, MAX_CWRU_REPORT_BYTES)
    validate_cwru_report(source)
    report_digest = _sha(_canonical_json(source).encode("utf-8"))
    metadata = source["metadata"]
    labels = source["labels"]
    series = source["series"]
    card = deepcopy(template_card("cwru"))
    card["instance_kind"] = "run"
    card["card_id"] += ":" + report_digest[:16]
    card["run_provenance"] = {
        "source_card_id": source["source_card_id"],
        "inspection_report_sha256": report_digest,
        "source_file_name": source["source_file_name"],
        "source_file_sha256": source["source_file_sha256"],
        "source_file_bytes": source["source_file_bytes"],
        "bearing_location": metadata["bearing_location"],
        "channel_variable": metadata["channel_variable"],
        "fault_type": labels["seeded_fault_type"],
        "fault_diameter_mils": labels["seeded_fault_diameter_mils"],
        "outer_race_position": metadata["outer_race_position"],
        "load_hp": metadata["load_hp"],
        "sample_rate_hz": metadata["sample_rate_hz"],
        "sample_count": series["sample_count"],
        "run_to_failure": False,
        "failure_time": None,
        "remaining_useful_life": None,
        "rights_status": "unverified_for_redistribution",
    }
    validate_card(card)
    return card


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce offline dataset cards; external-source cards remain local-only")
    parser.add_argument("--source", choices=("synthetic", "ims", "cwru"), required=True)
    parser.add_argument("--input", type=Path, required=True,
                        help="synthetic export directory OR local IMS/CWRU inspection report JSON")
    parser.add_argument("--out", type=Path, required=True, help="new JSON output; no overwrite")
    parser.add_argument("--verify-files", action="store_true",
                        help="IMS only: recheck local source record hashes")
    args = parser.parse_args()
    try:
        if args.source == "synthetic":
            if args.verify_files:
                raise ValueError("--verify-files requires --source ims")
            card = synthetic_run_card(args.input)
        elif args.source == "ims":
            card = ims_run_card(args.input, verify_files=args.verify_files)
        else:
            if args.verify_files:
                raise ValueError("--verify-files requires --source ims")
            card = cwru_run_card(args.input)
        write_local_manifest(args.out, card)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Generated {args.source} dataset card: {args.out} ({card['instance_kind']})")


if __name__ == "__main__":
    main()
