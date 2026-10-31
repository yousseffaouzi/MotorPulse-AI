"""Audit exact local physical feature files for a future experiment (MP-062).

The bundle is metadata-only. It binds MP-058 feature files to an exact MP-061
ready cohort, but it does not train, score, diagnose, deploy, or publish data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .physical_dataset import PARTITIONS, PUBLICATION_STATUS, _read_features
from .physical_training_readiness import (
    _read_json,
    assess_training_readiness,
    validate_readiness_assessment,
)

BUNDLE_VERSION = "1.0.0"
MAX_FEATURE_FILES = 1000
_BUNDLE_KEYS = frozenset(
    {
        "bundle_version",
        "bundle_id",
        "readiness_assessment_id",
        "readiness_assessment_sha256",
        "split_plan_sha256",
        "target_mode",
        "partitions",
        "source_files",
        "publication_status",
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _raw_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_feature_file(path: str | Path, card: dict[str, Any]) -> dict[str, Any]:
    source = Path(path)
    _require(
        source.is_file() and not source.is_symlink(),
        "physical feature file must be an existing non-symlink file",
    )
    rows, canonical_digest = _read_features(source)
    _require(
        canonical_digest == card["features_sha256"],
        "physical feature content does not match its run card",
    )
    _require(len(rows) == card["records"], "physical feature row count changed")
    counts = Counter(row["feature_status"] for row in rows)
    _require(
        counts.get("extracted", 0) == card["extracted_records"]
        and counts.get("abstained", 0) == card["abstained_records"],
        "physical feature status counts changed",
    )
    _require(
        {row["asset_id"] for row in rows} == {card["asset_id"]},
        "physical feature asset does not match run card",
    )
    _require(
        {row["device_id"] for row in rows} == {card["device_id"]},
        "physical feature device does not match run card",
    )
    sampling = sorted({(row["sample_rate_hz"], row["sample_count"]) for row in rows})
    expected_sampling = sorted(
        (item["sample_rate_hz"], item["sample_count"])
        for item in card["sampling_contracts"]
    )
    _require(
        sampling == expected_sampling, "physical feature sampling contract changed"
    )
    provenance = {
        json.dumps(
            row["provenance"],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for row in rows
    }
    expected_provenance = json.dumps(
        card["sensor_provenance"],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    _require(
        provenance == {expected_provenance},
        "physical feature sensor provenance changed",
    )
    return {
        "card_id": card["card_id"],
        "session_id": card["session_id"],
        "asset_id": card["asset_id"],
        "features_sha256": canonical_digest,
        "feature_file_sha256": _raw_sha256(source),
        "records": len(rows),
        "extracted_records": counts.get("extracted", 0),
        "abstained_records": counts.get("abstained", 0),
    }


def _build_bundle(
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
) -> dict[str, Any]:
    validate_readiness_assessment(readiness)
    recomputed = assess_training_readiness(
        split_plan,
        run_cards,
        review_manifests,
        target_mode=readiness["target_mode"],
    )
    _require(
        recomputed == readiness,
        "physical readiness assessment does not match supplied sources",
    )
    _require(
        readiness["training_readiness"] == "ready_for_review"
        and readiness["blockers"] == [],
        "physical experiment bundle requires MP-061 ready_for_review",
    )
    _require(
        type(feature_paths) in (list, tuple)
        and len(feature_paths) == len(run_cards)
        and 3 <= len(feature_paths) <= MAX_FEATURE_FILES,
        "need exactly one physical feature file per run card",
    )

    cards_by_digest = {card["features_sha256"]: card for card in run_cards}
    _require(
        len(cards_by_digest) == len(run_cards),
        "physical run cards contain duplicate feature content",
    )
    files_by_card: dict[str, dict[str, Any]] = {}
    raw_hashes: set[str] = set()
    for path in feature_paths:
        rows, digest = _read_features(path)
        del rows
        _require(
            digest in cards_by_digest,
            "physical feature file is not part of the ready cohort",
        )
        card = cards_by_digest[digest]
        _require(
            card["card_id"] not in files_by_card,
            "duplicate physical feature file for run card",
        )
        metadata = _verify_feature_file(path, card)
        _require(
            metadata["feature_file_sha256"] not in raw_hashes,
            "duplicate physical feature file bytes",
        )
        raw_hashes.add(metadata["feature_file_sha256"])
        files_by_card[card["card_id"]] = metadata
    _require(
        set(files_by_card) == {card["card_id"] for card in run_cards},
        "physical feature files do not cover every ready run card",
    )

    partitions: dict[str, list[dict[str, Any]]] = {}
    for partition_name in PARTITIONS:
        entries = [
            files_by_card[card_id]
            for card_id in split_plan["partitions"][partition_name]["card_ids"]
        ]
        partitions[partition_name] = sorted(
            entries,
            key=lambda item: (item["asset_id"], item["session_id"], item["card_id"]),
        )

    source_files = sorted(
        files_by_card.values(),
        key=lambda item: (item["asset_id"], item["session_id"], item["card_id"]),
    )
    body = {
        "bundle_version": BUNDLE_VERSION,
        "readiness_assessment_id": readiness["assessment_id"],
        "readiness_assessment_sha256": _sha(readiness),
        "split_plan_sha256": split_plan["plan_sha256"],
        "target_mode": readiness["target_mode"],
        "partitions": partitions,
        "source_files": source_files,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    return {"bundle_id": "physical-bundle:" + _sha(body)[:24], **body}


def create_experiment_bundle(
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Create a deterministic metadata-only audit of exact local feature files."""
    bundle = _build_bundle(
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
    )
    validate_experiment_bundle(
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
    )
    return bundle


def validate_experiment_bundle(
    bundle: Any,
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
) -> None:
    """Re-audit sources and reject any bundle/source mutation."""
    _require(
        type(bundle) is dict and set(bundle) == _BUNDLE_KEYS,
        "physical experiment bundle fields differ from v1 contract",
    )
    _require(bundle["bundle_version"] == BUNDLE_VERSION, "unsupported bundle version")
    expected = _build_bundle(
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
    )
    _require(bundle == expected, "physical experiment bundle does not match sources")
    _require(
        bundle["publication_status"] == PUBLICATION_STATUS,
        "physical experiment bundle publication boundary changed",
    )
    for field in (
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    ):
        _require(bundle[field] is False, f"MP-062 must keep {field}=false")


def audit_files(
    readiness_path: str | Path,
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    feature_paths: Sequence[str | Path],
) -> dict[str, Any]:
    readiness = _read_json(readiness_path, "physical readiness assessment")
    split_plan = _read_json(split_path, "physical split plan")
    cards = [_read_json(path, "physical run card") for path in card_paths]
    reviews = [_read_json(path, "physical evidence review") for path in review_paths]
    return create_experiment_bundle(
        readiness,
        split_plan,
        cards,
        reviews,
        feature_paths,
    )


def write_bundle(path: str | Path, bundle: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "bundle output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "bundle output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            bundle,
            stream,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit exact local physical feature files for a future experiment"
    )
    parser.add_argument("--readiness", required=True, help="MP-061 readiness JSON")
    parser.add_argument("--split", required=True, help="MP-059 split plan JSON")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--out", required=True, help="write-once bundle manifest JSON")
    args = parser.parse_args(argv)
    bundle = audit_files(
        args.readiness,
        args.split,
        args.cards,
        args.reviews,
        args.features,
    )
    write_bundle(args.out, bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
