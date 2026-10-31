"""Local-only physical dataset cards and whole-asset split planning (MP-059).

This module consumes MP-058 feature outputs. It does not train or score a model,
infer labels, redistribute physical measurements, or connect to hardware.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any, Sequence

from .physical_features import FEATURE_KEYS, FEATURE_SOURCE, FEATURE_VERSION, canonical_feature_bytes

CARD_VERSION = "1.0.0"
SPLIT_VERSION = "1.0.0"
DATASET_TYPE = "user_supplied_local_physical_features"
PUBLICATION_STATUS = "local_only_do_not_redistribute"
PARTITIONS = ("train", "validation", "test")
DEFAULT_RATIOS = (0.6, 0.2, 0.2)
MAX_CARDS = 1000
MAX_FEATURE_BYTES = 268_435_456
MAX_REPORT_BYTES = 262_144
MAX_CARD_BYTES = 262_144
MAX_TEXT = 128
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_ROW_KEYS = frozenset(
    {
        "feature_version",
        "source",
        "measurement_source",
        "device_id",
        "asset_id",
        "sequence",
        "device_uptime_ms",
        "captured_at_utc",
        "sample_rate_hz",
        "sample_count",
        "units",
        "quality",
        "temperature_c",
        "rpm",
        "provenance",
        "input_frame_sha256",
        "feature_status",
        "feature_status_reasons",
        "spectral_window",
        *FEATURE_KEYS,
    }
)
_CARD_KEYS = frozenset(
    {
        "card_version",
        "card_id",
        "dataset_type",
        "session_id",
        "asset_id",
        "device_id",
        "feature_version",
        "records",
        "extracted_records",
        "abstained_records",
        "captured_start_utc",
        "captured_end_utc",
        "sampling_contracts",
        "sensor_provenance",
        "features_sha256",
        "canonical_frames_sha256",
        "input_capture_sha256",
        "calibration_status",
        "label_status",
        "failure_evidence_status",
        "publication_status",
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    }
)


def _sha(value: Any) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _digest(value: Any, field: str) -> str:
    _require(type(value) is str and _SHA256.fullmatch(value) is not None, f"{field} must be lowercase SHA-256")
    return value


def _text(value: Any, field: str) -> str:
    _require(type(value) is str and 0 < len(value) <= MAX_TEXT, f"{field} must be 1-{MAX_TEXT} characters")
    _require(not any(ord(char) < 32 for char in value), f"{field} contains control characters")
    return value


def _utc(value: Any, field: str) -> datetime:
    _require(type(value) is str, f"{field} must be a UTC ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO 8601") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), f"{field} must use UTC")
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


def _strict_json(text: str, field: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {field} JSON") from exc
    _require(type(value) is dict, f"{field} must be a JSON object")
    return value


def _read_json(path: str | Path, *, limit: int, field: str) -> dict[str, Any]:
    source = Path(path)
    _require(source.is_file() and not source.is_symlink(), f"{field} must be an existing non-symlink file")
    size = source.stat().st_size
    _require(0 < size <= limit, f"{field} file size is empty or exceeds the limit")
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8") from exc
    return _strict_json(text, field)


def _validate_feature_row(row: dict[str, Any]) -> None:
    _require(type(row) is dict and set(row) == _ROW_KEYS, "physical feature row keys differ from v1 contract")
    _require(row["feature_version"] == FEATURE_VERSION, "unsupported physical feature version")
    _require(row["source"] == FEATURE_SOURCE, "invalid physical feature source")
    _require(row["measurement_source"] == "physical_sensor", "feature row must derive from physical_sensor")
    _text(row["device_id"], "device_id")
    _text(row["asset_id"], "asset_id")
    _require(type(row["sequence"]) is int and row["sequence"] > 0, "sequence must be positive integer")
    _require(type(row["device_uptime_ms"]) is int and row["device_uptime_ms"] >= 0, "device uptime must be nonnegative integer")
    _utc(row["captured_at_utc"], "captured_at_utc")
    _require(type(row["sample_rate_hz"]) is int and row["sample_rate_hz"] > 0, "sample rate must be positive integer")
    _require(type(row["sample_count"]) is int and row["sample_count"] > 0, "sample count must be positive integer")
    _digest(row["input_frame_sha256"], "input_frame_sha256")
    _require(type(row["provenance"]) is dict and row["provenance"], "sensor provenance must be nonempty")
    status = row["feature_status"]
    _require(status in ("extracted", "abstained"), "invalid feature status")
    reasons = row["feature_status_reasons"]
    _require(type(reasons) is list and all(type(reason) is str and reason for reason in reasons), "invalid feature status reasons")
    if status == "extracted":
        _require(not reasons and row["spectral_window"] == "hann", "extracted rows require Hann features without abstention reasons")
        for key in FEATURE_KEYS:
            _require(type(row[key]) in (int, float) and isfinite(row[key]), f"extracted {key} must be finite")
    else:
        _require(bool(reasons) and row["spectral_window"] is None, "abstained rows require reasons and no spectral window")
        _require(all(row[key] is None for key in FEATURE_KEYS), "abstained derived features must remain null")


def _validate_feature_report(report: dict[str, Any]) -> None:
    required = {
        "report_version",
        "feature_version",
        "source",
        "records",
        "feature_status_counts",
        "input_sha256",
        "canonical_frames_sha256",
        "features_sha256",
        "claims",
    }
    _require(set(report) == required, "physical feature report keys differ from v1 contract")
    _require(report["report_version"] == "1.0.0" and report["feature_version"] == FEATURE_VERSION, "unsupported physical feature report version")
    _require(report["source"] == FEATURE_SOURCE, "invalid feature report source")
    _require(type(report["records"]) is int and report["records"] > 0, "feature report records must be positive")
    for field in ("input_sha256", "canonical_frames_sha256", "features_sha256"):
        _digest(report[field], field)
    claims = report["claims"]
    _require(type(claims) is dict, "feature report claims must be an object")
    expected_claims = {
        "physical_features": True,
        "field_calibrated": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis": False,
        "failure_probability": False,
        "rul": False,
    }
    _require(claims == expected_claims, "physical feature report claim boundary changed")


def _read_features(path: str | Path) -> tuple[list[dict[str, Any]], str]:
    source = Path(path)
    _require(source.is_file() and not source.is_symlink(), "feature JSONL must be an existing non-symlink file")
    size = source.stat().st_size
    _require(0 < size <= MAX_FEATURE_BYTES, "feature JSONL size is empty or exceeds the limit")
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for line_number, raw in enumerate(stream, start=1):
            _require(raw.strip() != b"", f"feature row {line_number} is blank")
            try:
                row = _strict_json(raw.decode("utf-8"), f"feature row {line_number}")
            except UnicodeDecodeError as exc:
                raise ValueError(f"feature row {line_number} must be UTF-8") from exc
            _validate_feature_row(row)
            digest.update(canonical_feature_bytes(row))
            digest.update(b"\n")
            rows.append(row)
    _require(rows, "feature JSONL contains no rows")
    return rows, digest.hexdigest()


def create_run_card(
    features_path: str | Path,
    report_path: str | Path,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Bind one local physical acquisition session to verified MP-058 features."""
    session_id = _text(session_id, "session_id")
    report = _read_json(report_path, limit=MAX_REPORT_BYTES, field="feature report")
    _validate_feature_report(report)
    rows, feature_digest = _read_features(features_path)
    _require(feature_digest == report["features_sha256"], "feature JSONL SHA-256 does not match report")
    _require(len(rows) == report["records"], "feature row count does not match report")

    status_counts = Counter(row["feature_status"] for row in rows)
    _require(dict(sorted(status_counts.items())) == report["feature_status_counts"], "feature status counts do not match report")
    assets = {row["asset_id"] for row in rows}
    devices = {row["device_id"] for row in rows}
    _require(len(assets) == 1, "one physical run card must contain exactly one asset")
    _require(len(devices) == 1, "one physical run card must contain exactly one device")
    frame_hashes = [row["input_frame_sha256"] for row in rows]
    _require(len(frame_hashes) == len(set(frame_hashes)), "duplicate canonical input frame in physical session")

    ordered = sorted(rows, key=lambda row: row["sequence"])
    _require(ordered == rows, "physical feature rows must remain in strictly increasing sequence order")
    previous_sequence = 0
    previous_uptime = -1
    previous_time: datetime | None = None
    for row in rows:
        timestamp = _utc(row["captured_at_utc"], "captured_at_utc")
        _require(row["sequence"] > previous_sequence, "physical session sequence must strictly increase")
        _require(row["device_uptime_ms"] > previous_uptime, "physical session uptime must strictly increase")
        if previous_time is not None:
            _require(timestamp > previous_time, "physical session timestamps must strictly increase")
        previous_sequence = row["sequence"]
        previous_uptime = row["device_uptime_ms"]
        previous_time = timestamp

    provenance_values = {
        json.dumps(row["provenance"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for row in rows
    }
    _require(len(provenance_values) == 1, "one physical session must use one sensor/firmware provenance contract")
    provenance = rows[0]["provenance"]
    sampling = sorted({(row["sample_rate_hz"], row["sample_count"]) for row in rows})
    body = {
        "card_version": CARD_VERSION,
        "dataset_type": DATASET_TYPE,
        "session_id": session_id,
        "asset_id": next(iter(assets)),
        "device_id": next(iter(devices)),
        "feature_version": FEATURE_VERSION,
        "records": len(rows),
        "extracted_records": status_counts.get("extracted", 0),
        "abstained_records": status_counts.get("abstained", 0),
        "captured_start_utc": rows[0]["captured_at_utc"],
        "captured_end_utc": rows[-1]["captured_at_utc"],
        "sampling_contracts": [
            {"sample_rate_hz": rate, "sample_count": count} for rate, count in sampling
        ],
        "sensor_provenance": provenance,
        "features_sha256": report["features_sha256"],
        "canonical_frames_sha256": report["canonical_frames_sha256"],
        "input_capture_sha256": report["input_sha256"],
        "calibration_status": "unverified",
        "label_status": "unknown",
        "failure_evidence_status": "unknown",
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    card = {"card_id": "physical-run:" + _sha(body)[:24], **body}
    validate_run_card(card)
    return card


def validate_run_card(card: Any) -> None:
    """Validate a conservative local physical run card; unknown stays unknown."""
    _require(type(card) is dict and set(card) == _CARD_KEYS, "physical run card keys differ from v1 contract")
    _require(card["card_version"] == CARD_VERSION and card["dataset_type"] == DATASET_TYPE, "unsupported physical run card version/type")
    _require(type(card["card_id"]) is str and card["card_id"].startswith("physical-run:"), "invalid physical card ID")
    for field in ("session_id", "asset_id", "device_id"):
        _text(card[field], field)
    _require(card["feature_version"] == FEATURE_VERSION, "physical card feature version mismatch")
    for field in ("records", "extracted_records", "abstained_records"):
        _require(type(card[field]) is int and card[field] >= 0, f"{field} must be nonnegative integer")
    _require(card["records"] > 0 and card["extracted_records"] + card["abstained_records"] == card["records"], "physical card record counts are inconsistent")
    start = _utc(card["captured_start_utc"], "captured_start_utc")
    end = _utc(card["captured_end_utc"], "captured_end_utc")
    _require(end >= start, "physical card time bounds are reversed")
    _require(type(card["sampling_contracts"]) is list and card["sampling_contracts"], "physical card requires sampling contracts")
    _require(type(card["sensor_provenance"]) is dict and card["sensor_provenance"], "physical card requires sensor provenance")
    for field in ("features_sha256", "canonical_frames_sha256", "input_capture_sha256"):
        _digest(card[field], field)
    _require(card["calibration_status"] == "unverified", "MP-059 cannot promote calibration status")
    _require(card["label_status"] == "unknown", "MP-059 cannot promote physical labels")
    _require(card["failure_evidence_status"] == "unknown", "MP-059 cannot promote failure evidence")
    _require(card["publication_status"] == PUBLICATION_STATUS and card["redistribution_cleared"] is False, "physical measurements remain local-only")
    for field in ("training_authorized", "model_scoring_authorized", "diagnosis_authorized", "rul_authorized"):
        _require(card[field] is False, f"MP-059 must keep {field}=false")
    body = {key: value for key, value in card.items() if key != "card_id"}
    _require(card["card_id"] == "physical-run:" + _sha(body)[:24], "physical card ID does not match canonical content")


def _ratios(value: Sequence[float]) -> tuple[float, float, float]:
    _require(isinstance(value, (list, tuple)) and len(value) == 3, "ratios must be train, validation, test")
    _require(all(type(part) in (int, float) and isfinite(part) and part > 0 for part in value), "ratios must be positive finite numbers")
    _require(abs(sum(value) - 1) <= 1e-9, "split ratios must sum to one")
    return tuple(float(part) for part in value)


def _allocate(count: int, ratios: Sequence[float]) -> tuple[int, int, int]:
    _require(type(count) is int and count >= 3, "at least three independent physical assets are required")
    values = _ratios(ratios)
    exact = [count * portion for portion in values]
    allocated = [1, 1, 1]
    for _ in range(count - 3):
        candidate = max(range(3), key=lambda index: (exact[index] - allocated[index], -index))
        allocated[candidate] += 1
    return tuple(allocated)


def _load_card(path: str | Path) -> dict[str, Any]:
    card = _read_json(path, limit=MAX_CARD_BYTES, field="physical run card")
    validate_run_card(card)
    return card


def asset_split(
    card_paths: Sequence[str | Path],
    *,
    seed: int = 42,
    ratios: Sequence[float] = DEFAULT_RATIOS,
) -> dict[str, Any]:
    """Assign complete physical assets, with all sessions, to one partition."""
    _ratios(ratios)
    _require(type(seed) is int and 0 <= seed <= 2**32 - 1, "split seed must be an integer in [0, 2^32-1]")
    _require(isinstance(card_paths, (list, tuple)) and 3 <= len(card_paths) <= MAX_CARDS, f"need 3-{MAX_CARDS} physical run cards")
    cards = [_load_card(path) for path in card_paths]
    card_ids = [card["card_id"] for card in cards]
    session_ids = [card["session_id"] for card in cards]
    feature_hashes = [card["features_sha256"] for card in cards]
    _require(len(card_ids) == len(set(card_ids)), "duplicate physical run card identity")
    _require(len(session_ids) == len(set(session_ids)), "duplicate physical acquisition session identity")
    _require(len(feature_hashes) == len(set(feature_hashes)), "duplicate physical feature content across sessions")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        groups[card["asset_id"]].append(card)
    _require(len(groups) >= 3, "at least three distinct physical assets are required")
    amounts = _allocate(len(groups), ratios)
    ordered_assets = sorted(
        groups,
        key=lambda asset_id: (
            hashlib.sha256(f"{seed}:{asset_id}".encode("utf-8")).hexdigest(),
            asset_id,
        ),
    )
    partitions: dict[str, Any] = {}
    start = 0
    for name, amount in zip(PARTITIONS, amounts):
        selected_assets = ordered_assets[start : start + amount]
        selected_cards = [card for asset in selected_assets for card in groups[asset]]
        partitions[name] = {
            "asset_ids": sorted(selected_assets),
            "card_ids": sorted(card["card_id"] for card in selected_cards),
            "session_ids": sorted(card["session_id"] for card in selected_cards),
            "assets": len(selected_assets),
            "sessions": len(selected_cards),
            "records": sum(card["records"] for card in selected_cards),
            "extracted_records": sum(card["extracted_records"] for card in selected_cards),
            "abstained_records": sum(card["abstained_records"] for card in selected_cards),
        }
        start += amount

    sources = [
        {
            "card_id": card["card_id"],
            "session_id": card["session_id"],
            "asset_id": card["asset_id"],
            "device_id": card["device_id"],
            "features_sha256": card["features_sha256"],
            "records": card["records"],
            "calibration_status": card["calibration_status"],
            "label_status": card["label_status"],
            "failure_evidence_status": card["failure_evidence_status"],
        }
        for card in sorted(cards, key=lambda item: (item["asset_id"], item["session_id"], item["card_id"]))
    ]
    manifest = {
        "split_version": SPLIT_VERSION,
        "policy": "whole_physical_asset_grouped",
        "dataset_type": DATASET_TYPE,
        "seed": seed,
        "ratios": list(_ratios(ratios)),
        "group_boundary": "all acquisition sessions and feature rows for one physical asset remain in exactly one partition",
        "partitions": partitions,
        "sources": sources,
        "label_blind_assignment": True,
        "label_policy": "physical labels and failure evidence remain unknown; this plan must not infer or promote them",
        "preprocessing_rule": "if a later reviewed milestone authorizes training, fit transforms and select thresholds on training assets only",
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
    }
    manifest["plan_sha256"] = _sha(manifest)
    return manifest


def write_json(path: str | Path, value: dict[str, Any]) -> None:
    destination = Path(path)
    _require(not destination.exists() and not destination.is_symlink(), "output already exists; refusing to overwrite")
    _require(destination.parent.is_dir() and not destination.parent.is_symlink(), "output parent must exist and not be a symlink")
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create local-only physical dataset cards and whole-asset split plans")
    subparsers = parser.add_subparsers(dest="command", required=True)
    card_parser = subparsers.add_parser("card", help="bind one MP-058 feature session to a conservative run card")
    card_parser.add_argument("--features", required=True)
    card_parser.add_argument("--report", required=True)
    card_parser.add_argument("--session-id", required=True)
    card_parser.add_argument("--out", required=True)
    split_parser = subparsers.add_parser("split", help="split complete physical assets without leakage")
    split_parser.add_argument("--card", action="append", required=True, dest="cards")
    split_parser.add_argument("--out", required=True)
    split_parser.add_argument("--seed", type=int, default=42)
    split_parser.add_argument("--train-ratio", type=float, default=0.6)
    split_parser.add_argument("--validation-ratio", type=float, default=0.2)
    split_parser.add_argument("--test-ratio", type=float, default=0.2)
    args = parser.parse_args(argv)
    if args.command == "card":
        value = create_run_card(args.features, args.report, session_id=args.session_id)
    else:
        value = asset_split(
            args.cards,
            seed=args.seed,
            ratios=(args.train_ratio, args.validation_ratio, args.test_ratio),
        )
    write_json(args.out, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
