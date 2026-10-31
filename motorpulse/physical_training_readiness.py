"""Offline physical training-readiness assessment contract (MP-061).

This module verifies MP-059 physical run cards/splits and MP-060 evidence reviews.
It can mark a cohort ready for a later training review, but it never authorizes,
fits, scores, diagnoses, deploys, or publishes a physical-data model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Sequence

from .physical_dataset import (
    DATASET_TYPE,
    MAX_CARDS,
    PARTITIONS,
    PUBLICATION_STATUS,
    SPLIT_VERSION,
    validate_run_card,
)
from .physical_evidence import REVIEW_VERSION, validate_review_manifest

READINESS_VERSION = "1.0.0"
TARGET_MODES = ("unsupervised_anomaly", "supervised_failure")
MAX_JSON_BYTES = 262_144
MAX_INPUTS = MAX_CARDS
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SPLIT_KEYS = frozenset(
    {
        "split_version",
        "policy",
        "dataset_type",
        "seed",
        "ratios",
        "group_boundary",
        "partitions",
        "sources",
        "label_blind_assignment",
        "label_policy",
        "preprocessing_rule",
        "publication_status",
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "plan_sha256",
    }
)
_PARTITION_KEYS = frozenset(
    {
        "asset_ids",
        "card_ids",
        "session_ids",
        "assets",
        "sessions",
        "records",
        "extracted_records",
        "abstained_records",
    }
)
_SOURCE_KEYS = frozenset(
    {
        "card_id",
        "session_id",
        "asset_id",
        "device_id",
        "features_sha256",
        "records",
        "calibration_status",
        "label_status",
        "failure_evidence_status",
    }
)
_ASSESSMENT_KEYS = frozenset(
    {
        "readiness_version",
        "assessment_id",
        "target_mode",
        "training_readiness",
        "blockers",
        "split_plan_sha256",
        "feature_contract",
        "evidence_policy",
        "partition_summary",
        "source_bindings",
        "preprocessing_policy",
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


def _digest(value: Any, field: str) -> str:
    _require(
        type(value) is str and _SHA256.fullmatch(value) is not None,
        f"{field} must be lowercase SHA-256",
    )
    return value


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


def _read_json(path: str | Path, field: str) -> dict[str, Any]:
    source = Path(path)
    _require(
        source.is_file() and not source.is_symlink(),
        f"{field} must be an existing non-symlink file",
    )
    size = source.stat().st_size
    _require(0 < size <= MAX_JSON_BYTES, f"{field} file size is invalid")
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8") from exc
    return _strict_json(text, field)


def _validate_split_plan(plan: Any, cards: Sequence[dict[str, Any]]) -> dict[str, str]:
    _require(
        type(plan) is dict and set(plan) == _SPLIT_KEYS,
        "physical split plan fields differ from MP-059 contract",
    )
    _require(
        plan["split_version"] == SPLIT_VERSION, "unsupported physical split version"
    )
    _require(
        plan["policy"] == "whole_physical_asset_grouped",
        "invalid physical split policy",
    )
    _require(
        plan["dataset_type"] == DATASET_TYPE, "physical split dataset type mismatch"
    )
    _require(
        type(plan["seed"]) is int and 0 <= plan["seed"] <= 2**32 - 1,
        "physical split seed is invalid",
    )
    ratios = plan["ratios"]
    _require(
        type(ratios) is list
        and len(ratios) == 3
        and all(type(value) in (int, float) and value > 0 for value in ratios)
        and abs(sum(ratios) - 1) <= 1e-9,
        "physical split ratios are invalid",
    )
    _require(
        plan["label_blind_assignment"] is True,
        "physical split must remain label-blind",
    )
    _require(
        plan["publication_status"] == PUBLICATION_STATUS
        and plan["redistribution_cleared"] is False,
        "physical split publication boundary changed",
    )
    _require(
        plan["training_authorized"] is False
        and plan["model_scoring_authorized"] is False,
        "MP-059 split cannot authorize training or scoring",
    )
    expected_hash = _sha(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    _require(
        plan["plan_sha256"] == expected_hash,
        "physical split plan SHA-256 does not match canonical content",
    )

    _require(
        type(cards) in (list, tuple) and 3 <= len(cards) <= MAX_INPUTS,
        f"need 3-{MAX_INPUTS} physical run cards",
    )
    for card in cards:
        validate_run_card(card)
    card_ids = [card["card_id"] for card in cards]
    session_ids = [card["session_id"] for card in cards]
    feature_hashes = [card["features_sha256"] for card in cards]
    _require(
        len(card_ids) == len(set(card_ids)), "duplicate physical run card identity"
    )
    _require(
        len(session_ids) == len(set(session_ids)), "duplicate physical session identity"
    )
    _require(
        len(feature_hashes) == len(set(feature_hashes)),
        "duplicate physical feature content across sessions",
    )

    expected_sources = [
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
        for card in sorted(
            cards,
            key=lambda item: (item["asset_id"], item["session_id"], item["card_id"]),
        )
    ]
    _require(
        type(plan["sources"]) is list
        and all(
            type(source) is dict and set(source) == _SOURCE_KEYS
            for source in plan["sources"]
        ),
        "physical split sources differ from MP-059 contract",
    )
    _require(
        plan["sources"] == expected_sources,
        "physical split sources do not match supplied cards",
    )

    partitions = plan["partitions"]
    _require(
        type(partitions) is dict and set(partitions) == set(PARTITIONS),
        "physical split partitions differ from train/validation/test",
    )
    cards_by_id = {card["card_id"]: card for card in cards}
    asset_partition: dict[str, str] = {}
    seen_cards: set[str] = set()
    seen_sessions: set[str] = set()
    for partition_name in PARTITIONS:
        partition = partitions[partition_name]
        _require(
            type(partition) is dict and set(partition) == _PARTITION_KEYS,
            f"{partition_name} partition fields differ from MP-059 contract",
        )
        asset_ids = partition["asset_ids"]
        partition_card_ids = partition["card_ids"]
        partition_sessions = partition["session_ids"]
        _require(
            type(asset_ids) is list
            and asset_ids
            and len(asset_ids) == len(set(asset_ids)),
            f"{partition_name} asset IDs must be nonempty and unique",
        )
        _require(
            type(partition_card_ids) is list
            and partition_card_ids
            and len(partition_card_ids) == len(set(partition_card_ids)),
            f"{partition_name} card IDs must be nonempty and unique",
        )
        _require(
            type(partition_sessions) is list
            and partition_sessions
            and len(partition_sessions) == len(set(partition_sessions)),
            f"{partition_name} session IDs must be nonempty and unique",
        )
        _require(
            seen_cards.isdisjoint(partition_card_ids),
            "physical run card appears in multiple partitions",
        )
        _require(
            seen_sessions.isdisjoint(partition_sessions),
            "physical session appears in multiple partitions",
        )
        for asset_id in asset_ids:
            _require(
                asset_id not in asset_partition,
                "physical asset leaks across partitions",
            )
            asset_partition[asset_id] = partition_name
        selected = [
            cards_by_id[card_id]
            for card_id in partition_card_ids
            if card_id in cards_by_id
        ]
        _require(
            len(selected) == len(partition_card_ids),
            f"{partition_name} references unknown run card",
        )
        _require(
            sorted(
                card["asset_id"] for card in selected if card["asset_id"] in asset_ids
            ),
            f"{partition_name} has no matching asset/card membership",
        )
        _require(
            sorted(set(card["asset_id"] for card in selected)) == sorted(asset_ids),
            f"{partition_name} asset IDs do not match card membership",
        )
        _require(
            sorted(card["session_id"] for card in selected)
            == sorted(partition_sessions),
            f"{partition_name} session IDs do not match card membership",
        )
        expected_counts = {
            "assets": len(asset_ids),
            "sessions": len(selected),
            "records": sum(card["records"] for card in selected),
            "extracted_records": sum(
                card["extracted_records"] for card in selected
            ),
            "abstained_records": sum(
                card["abstained_records"] for card in selected
            ),
        }
        for field, expected in expected_counts.items():
            _require(
                partition[field] == expected,
                f"{partition_name} {field} count does not match supplied cards",
            )
        seen_cards.update(partition_card_ids)
        seen_sessions.update(partition_sessions)

    _require(
        seen_cards == set(card_ids),
        "physical split does not cover every supplied run card",
    )
    _require(
        seen_sessions == set(session_ids),
        "physical split does not cover every supplied session",
    )
    _require(
        set(asset_partition) == {card["asset_id"] for card in cards},
        "physical split does not cover every supplied asset",
    )
    for card in cards:
        _require(
            card["card_id"]
            in partitions[asset_partition[card["asset_id"]]]["card_ids"],
            "physical card partition conflicts with its asset partition",
        )
    return asset_partition


def assess_training_readiness(
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    *,
    target_mode: str = "unsupervised_anomaly",
) -> dict[str, Any]:
    """Assess readiness for a later training review without authorizing training."""
    _require(target_mode in TARGET_MODES, "unsupported physical target mode")
    asset_partition = _validate_split_plan(split_plan, run_cards)
    _require(
        type(review_manifests) in (list, tuple)
        and len(review_manifests) == len(run_cards),
        "need exactly one physical evidence review per run card",
    )
    cards_by_id = {card["card_id"]: card for card in run_cards}
    reviews_by_card: dict[str, dict[str, Any]] = {}
    for review in review_manifests:
        _require(type(review) is dict, "physical evidence review must be an object")
        run_card_id = review.get("run_card_id")
        _require(
            run_card_id in cards_by_id,
            "physical evidence review references unknown run card",
        )
        _require(
            run_card_id not in reviews_by_card,
            "duplicate physical evidence review for run card",
        )
        validate_review_manifest(review, cards_by_id[run_card_id])
        _require(
            review["review_version"] == REVIEW_VERSION,
            "physical evidence review version mismatch",
        )
        reviews_by_card[run_card_id] = review
    _require(
        set(reviews_by_card) == set(cards_by_id),
        "physical evidence reviews do not cover every run card",
    )

    canonical_sampling = _canonical_bytes(run_cards[0]["sampling_contracts"])
    feature_version = run_cards[0]["feature_version"]
    blockers: list[str] = []
    bindings: list[dict[str, Any]] = []
    for card in sorted(
        run_cards,
        key=lambda item: (item["asset_id"], item["session_id"], item["card_id"]),
    ):
        review = reviews_by_card[card["card_id"]]
        categories = review["categories"]
        if categories["calibration"]["review_status"] != "reviewed":
            blockers.append(f"missing_calibration_review:{card['session_id']}")
        if categories["rights_privacy"]["review_status"] != "reviewed":
            blockers.append(f"missing_rights_privacy_review:{card['session_id']}")
        if (
            target_mode == "supervised_failure"
            and categories["label_failure"]["review_status"] != "reviewed"
        ):
            blockers.append(f"missing_label_failure_review:{card['session_id']}")
        if card["feature_version"] != feature_version:
            blockers.append(f"incompatible_feature_version:{card['session_id']}")
        if _canonical_bytes(card["sampling_contracts"]) != canonical_sampling:
            blockers.append(f"incompatible_sampling_contract:{card['session_id']}")
        if card["extracted_records"] <= 0:
            blockers.append(f"no_extracted_records:{card['session_id']}")
        bindings.append(
            {
                "card_id": card["card_id"],
                "card_sha256": _sha(card),
                "review_id": review["review_id"],
                "review_sha256": _sha(review),
                "session_id": card["session_id"],
                "asset_id": card["asset_id"],
                "partition": asset_partition[card["asset_id"]],
                "features_sha256": card["features_sha256"],
            }
        )

    blockers = sorted(set(blockers))
    body = {
        "readiness_version": READINESS_VERSION,
        "target_mode": target_mode,
        "training_readiness": "ready_for_review" if not blockers else "blocked",
        "blockers": blockers,
        "split_plan_sha256": split_plan["plan_sha256"],
        "feature_contract": {
            "feature_version": feature_version,
            "sampling_contracts": run_cards[0]["sampling_contracts"],
        },
        "evidence_policy": {
            "calibration_review_required": True,
            "rights_privacy_review_required": True,
            "label_failure_review_required": target_mode == "supervised_failure",
            "signal_derived_truth_allowed": False,
        },
        "partition_summary": {
            name: {
                "assets": split_plan["partitions"][name]["assets"],
                "sessions": split_plan["partitions"][name]["sessions"],
                "records": split_plan["partitions"][name]["records"],
                "extracted_records": split_plan["partitions"][name][
                    "extracted_records"
                ],
                "abstained_records": split_plan["partitions"][name][
                    "abstained_records"
                ],
            }
            for name in PARTITIONS
        },
        "source_bindings": bindings,
        "preprocessing_policy": "fit preprocessing and thresholds on training assets only; use validation for selection and keep test assets untouched until final evaluation",
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    assessment = {"assessment_id": "physical-readiness:" + _sha(body)[:24], **body}
    validate_readiness_assessment(assessment)
    return assessment


def validate_readiness_assessment(assessment: Any) -> None:
    """Validate the immutable MP-061 authorization and output boundary."""
    _require(
        type(assessment) is dict and set(assessment) == _ASSESSMENT_KEYS,
        "physical readiness assessment fields differ from v1 contract",
    )
    _require(
        assessment["readiness_version"] == READINESS_VERSION,
        "unsupported physical readiness version",
    )
    _require(
        assessment["target_mode"] in TARGET_MODES, "unsupported physical target mode"
    )
    blockers = assessment["blockers"]
    _require(
        type(blockers) is list
        and blockers == sorted(set(blockers))
        and all(type(blocker) is str and blocker for blocker in blockers),
        "physical readiness blockers must be deterministic unique strings",
    )
    expected_status = "ready_for_review" if not blockers else "blocked"
    _require(
        assessment["training_readiness"] == expected_status,
        "physical readiness status is inconsistent with blockers",
    )
    _digest(assessment["split_plan_sha256"], "split_plan_sha256")
    _require(
        assessment["publication_status"] == PUBLICATION_STATUS,
        "physical readiness publication boundary changed",
    )
    for field in (
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    ):
        _require(assessment[field] is False, f"MP-061 must keep {field}=false")
    body = {key: value for key, value in assessment.items() if key != "assessment_id"}
    _require(
        assessment["assessment_id"] == "physical-readiness:" + _sha(body)[:24],
        "physical readiness assessment ID does not match canonical content",
    )


def assess_files(
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    *,
    target_mode: str,
) -> dict[str, Any]:
    _require(
        type(card_paths) in (list, tuple) and type(review_paths) in (list, tuple),
        "card and review paths must be lists",
    )
    _require(
        3 <= len(card_paths) <= MAX_INPUTS and len(review_paths) == len(card_paths),
        f"need 3-{MAX_INPUTS} cards with exactly one review each",
    )
    split_plan = _read_json(split_path, "physical split plan")
    cards = [_read_json(path, "physical run card") for path in card_paths]
    reviews = [_read_json(path, "physical evidence review") for path in review_paths]
    return assess_training_readiness(
        split_plan,
        cards,
        reviews,
        target_mode=target_mode,
    )


def write_assessment(path: str | Path, assessment: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "readiness output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "readiness output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            assessment,
            stream,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assess a local physical cohort for a later model-training review"
    )
    parser.add_argument("--split", required=True, help="MP-059 physical split plan")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument(
        "--target-mode",
        choices=TARGET_MODES,
        default="unsupervised_anomaly",
    )
    parser.add_argument("--out", required=True, help="write-once readiness JSON")
    args = parser.parse_args(argv)
    assessment = assess_files(
        args.split,
        args.cards,
        args.reviews,
        target_mode=args.target_mode,
    )
    write_assessment(args.out, assessment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
