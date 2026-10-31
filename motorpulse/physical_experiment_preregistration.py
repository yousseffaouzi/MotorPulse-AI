"""Preregister a future physical anomaly experiment without training (MP-063).

This module revalidates an exact MP-062 bundle and freezes the first physical
experiment design. It can mark a design eligible for explicit training approval,
but it never grants that approval, fits, scores, diagnoses, deploys, or publishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .feature_pipeline import FEATURES
from .physical_dataset import PARTITIONS, PUBLICATION_STATUS
from .physical_experiment_bundle import validate_experiment_bundle
from .physical_training_readiness import _read_json

PREREGISTRATION_VERSION = "1.0.0"
PROTOCOL_VERSION = "1.0.0"
MODEL_FAMILY = "standardized_distance_baseline_v1"
MIN_QUANTILE = 0.90
MAX_QUANTILE = 0.999
MAX_MINIMUM_RECORDS = 10_000_000
_PROTOCOL_KEYS = frozenset(
    {
        "protocol_version",
        "model_family",
        "threshold_quantile",
        "seed",
        "minimum_extracted_records",
    }
)
_PREREGISTRATION_KEYS = frozenset(
    {
        "preregistration_version",
        "preregistration_id",
        "source_bundle_id",
        "source_bundle_sha256",
        "readiness_assessment_id",
        "split_plan_sha256",
        "protocol_sha256",
        "target_mode",
        "authorization_state",
        "blockers",
        "experiment_design",
        "partition_summary",
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


def _validate_protocol(protocol: Any) -> dict[str, Any]:
    _require(
        type(protocol) is dict and set(protocol) == _PROTOCOL_KEYS,
        "physical experiment protocol fields differ from MP-063 contract",
    )
    _require(
        protocol["protocol_version"] == PROTOCOL_VERSION,
        "unsupported physical experiment protocol version",
    )
    _require(
        protocol["model_family"] == MODEL_FAMILY,
        "unsupported physical experiment model family",
    )
    quantile = protocol["threshold_quantile"]
    _require(
        type(quantile) in (int, float)
        and MIN_QUANTILE <= float(quantile) <= MAX_QUANTILE,
        f"threshold_quantile must be between {MIN_QUANTILE} and {MAX_QUANTILE}",
    )
    seed = protocol["seed"]
    _require(
        type(seed) is int and 0 <= seed <= 2**32 - 1,
        "physical experiment seed must be a uint32 integer",
    )
    minimums = protocol["minimum_extracted_records"]
    _require(
        type(minimums) is dict and set(minimums) == set(PARTITIONS),
        "minimum_extracted_records must contain train, validation, and test",
    )
    for partition in PARTITIONS:
        value = minimums[partition]
        _require(
            type(value) is int and 1 <= value <= MAX_MINIMUM_RECORDS,
            f"{partition} minimum extracted records is invalid",
        )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "model_family": MODEL_FAMILY,
        "threshold_quantile": float(quantile),
        "seed": seed,
        "minimum_extracted_records": {
            partition: minimums[partition] for partition in PARTITIONS
        },
    }


def _partition_summary(bundle: dict[str, Any]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for partition in PARTITIONS:
        entries = bundle["partitions"][partition]
        summary[partition] = {
            "files": len(entries),
            "records": sum(entry["records"] for entry in entries),
            "extracted_records": sum(
                entry["extracted_records"] for entry in entries
            ),
            "abstained_records": sum(
                entry["abstained_records"] for entry in entries
            ),
        }
    return summary


def _build_preregistration(
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    validate_experiment_bundle(
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
    )
    normalized_protocol = _validate_protocol(protocol)
    summary = _partition_summary(bundle)
    blockers: list[str] = []
    if bundle["target_mode"] != "unsupervised_anomaly":
        blockers.append(f"unsupported_target_mode:{bundle['target_mode']}")
    for partition in PARTITIONS:
        actual = summary[partition]["extracted_records"]
        required = normalized_protocol["minimum_extracted_records"][partition]
        if actual < required:
            blockers.append(
                f"insufficient_{partition}_extracted_records:{actual}<{required}"
            )

    experiment_design = {
        "model_family": MODEL_FAMILY,
        "input_features": list(FEATURES),
        "fit_partition": "train",
        "preprocessing_fit_partition": "train",
        "threshold_partition": "train",
        "threshold_quantile": normalized_protocol["threshold_quantile"],
        "validation_role": "review_only_no_fit",
        "test_role": "final_only_no_fit",
        "seed": normalized_protocol["seed"],
        "minimum_extracted_records": normalized_protocol[
            "minimum_extracted_records"
        ],
    }
    body = {
        "preregistration_version": PREREGISTRATION_VERSION,
        "source_bundle_id": bundle["bundle_id"],
        "source_bundle_sha256": _sha(bundle),
        "readiness_assessment_id": readiness["assessment_id"],
        "split_plan_sha256": split_plan["plan_sha256"],
        "protocol_sha256": _sha(normalized_protocol),
        "target_mode": bundle["target_mode"],
        "authorization_state": (
            "blocked" if blockers else "eligible_for_explicit_training_approval"
        ),
        "blockers": blockers,
        "experiment_design": experiment_design,
        "partition_summary": summary,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    return {
        "preregistration_id": "physical-preregistration:" + _sha(body)[:24],
        **body,
    }


def create_preregistration(
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Create a deterministic preregistration without granting authorization."""
    preregistration = _build_preregistration(
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    validate_preregistration(
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    return preregistration


def validate_preregistration(
    preregistration: Any,
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> None:
    """Recompute the preregistration and reject source/protocol mutation."""
    _require(
        type(preregistration) is dict
        and set(preregistration) == _PREREGISTRATION_KEYS,
        "physical experiment preregistration fields differ from v1 contract",
    )
    _require(
        preregistration["preregistration_version"] == PREREGISTRATION_VERSION,
        "unsupported physical experiment preregistration version",
    )
    _require(
        preregistration["publication_status"] == PUBLICATION_STATUS,
        "physical experiment preregistration publication boundary changed",
    )
    for field in (
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    ):
        _require(preregistration[field] is False, f"MP-063 must keep {field}=false")
    expected = _build_preregistration(
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    _require(
        preregistration == expected,
        "physical experiment preregistration does not match sources and protocol",
    )


def preregister_files(
    bundle_path: str | Path,
    readiness_path: str | Path,
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    feature_paths: Sequence[str | Path],
    protocol_path: str | Path,
) -> dict[str, Any]:
    bundle = _read_json(bundle_path, "physical experiment bundle")
    readiness = _read_json(readiness_path, "physical readiness assessment")
    split_plan = _read_json(split_path, "physical split plan")
    cards = [_read_json(path, "physical run card") for path in card_paths]
    reviews = [_read_json(path, "physical evidence review") for path in review_paths]
    protocol = _read_json(protocol_path, "physical experiment protocol")
    return create_preregistration(
        bundle,
        readiness,
        split_plan,
        cards,
        reviews,
        feature_paths,
        protocol,
    )


def write_preregistration(path: str | Path, preregistration: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "preregistration output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "preregistration output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            preregistration,
            stream,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preregister a future physical anomaly experiment without training"
    )
    parser.add_argument("--bundle", required=True, help="MP-062 bundle JSON")
    parser.add_argument("--readiness", required=True, help="MP-061 readiness JSON")
    parser.add_argument("--split", required=True, help="MP-059 split plan JSON")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True, help="MP-063 protocol JSON")
    parser.add_argument("--out", required=True, help="write-once preregistration JSON")
    args = parser.parse_args(argv)
    preregistration = preregister_files(
        args.bundle,
        args.readiness,
        args.split,
        args.cards,
        args.reviews,
        args.features,
        args.protocol,
    )
    write_preregistration(args.out, preregistration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
