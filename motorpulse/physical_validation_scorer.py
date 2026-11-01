"""Score approved physical validation rows with the frozen MP-066 model (MP-069).

This module is deliberately validation-only. It requires the complete MP-068
approval/source chain, never refits or recalibrates, never touches the test
partition for scoring, and emits review-only anomaly scores rather than diagnoses.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .physical_dataset import PUBLICATION_STATUS, _read_features
from .physical_evaluation_approval_record import validate_evaluation_approval_record
from .physical_offline_trainer import _score, _vector
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json

VALIDATION_RESULT_VERSION = "1.0.0"
PARTITION = "validation"
RESULT_KIND = "review_only_anomaly_scores"
_ROW_KEYS = frozenset(
    {
        "card_id",
        "sequence",
        "input_frame_sha256",
        "status",
        "score",
        "review_flag",
    }
)
_RESULT_KEYS = frozenset(
    {
        "physical_validation_result_version",
        "result_id",
        "result_kind",
        "partition",
        "model_id",
        "model_sha256",
        "evaluation_approval_record_id",
        "evaluation_approval_record_sha256",
        "evaluation_request_id",
        "model_family",
        "score_direction",
        "score_is_failure_probability",
        "threshold",
        "threshold_source",
        "threshold_comparison",
        "rows",
        "counts",
        "train_rows_consumed",
        "test_rows_consumed",
        "model_refit_performed",
        "preprocessing_refit_performed",
        "threshold_recalibration_performed",
        "diagnosis_performed",
        "failure_probability_estimated",
        "rul_estimated",
        "publication_status",
        "redistribution_cleared",
        "validation_scoring_authorized",
        "validation_scoring_completed",
        "test_scoring_authorized",
        "deployment_authorized",
    }
)


def _validation_rows(
    bundle: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
) -> tuple[list[tuple[str, dict[str, Any]]], int]:
    cards_by_digest = {card["features_sha256"]: card for card in run_cards}
    _require(
        len(cards_by_digest) == len(run_cards),
        "physical validation run cards contain duplicate feature content",
    )
    rows_by_card: dict[str, list[dict[str, Any]]] = {}
    for path in feature_paths:
        rows, digest = _read_features(path)
        _require(
            digest in cards_by_digest,
            "physical validation feature file is outside the approved cohort",
        )
        card_id = cards_by_digest[digest]["card_id"]
        _require(
            card_id not in rows_by_card,
            "duplicate physical validation feature file for run card",
        )
        rows_by_card[card_id] = rows

    _require(
        set(rows_by_card) == {card["card_id"] for card in run_cards},
        "physical validation feature files do not cover the approved cohort",
    )
    validation_card_ids = sorted(split_plan["partitions"][PARTITION]["card_ids"])
    expected_validation_ids = sorted(
        entry["card_id"] for entry in bundle["partitions"][PARTITION]
    )
    _require(
        validation_card_ids == expected_validation_ids,
        "physical validation partition differs from approved bundle",
    )

    extracted: list[tuple[str, dict[str, Any]]] = []
    abstained = 0
    seen: set[tuple[str, int, str]] = set()
    for card_id in validation_card_ids:
        _require(card_id in rows_by_card, "approved validation feature file is missing")
        for row in rows_by_card[card_id]:
            identity = (card_id, row["sequence"], row["input_frame_sha256"])
            _require(identity not in seen, "duplicate physical validation row identity")
            seen.add(identity)
            if row["feature_status"] == "abstained":
                abstained += 1
                continue
            _vector(row)
            extracted.append((card_id, row))

    expected_extracted = sum(
        entry["extracted_records"] for entry in bundle["partitions"][PARTITION]
    )
    expected_abstained = sum(
        entry["abstained_records"] for entry in bundle["partitions"][PARTITION]
    )
    _require(
        len(extracted) == expected_extracted and abstained == expected_abstained,
        "physical validation row counts differ from approved validation partition",
    )
    return extracted, abstained


def _result_rows(
    extracted: Sequence[tuple[str, dict[str, Any]]],
    model: dict[str, Any],
) -> list[dict[str, Any]]:
    centers = model["preprocessing"]["center"]
    scales = model["preprocessing"]["effective_scales"]
    threshold = float(model["calibration"]["threshold"])
    rows: list[dict[str, Any]] = []
    for card_id, row in extracted:
        score = _score(_vector(row), centers, scales)
        rows.append(
            {
                "card_id": card_id,
                "sequence": row["sequence"],
                "input_frame_sha256": row["input_frame_sha256"],
                "status": "scored",
                "score": score,
                "review_flag": score > threshold,
            }
        )
    rows.sort(
        key=lambda item: (item["card_id"], item["sequence"], item["input_frame_sha256"])
    )
    return rows


def _abstained_rows(
    bundle: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
) -> list[dict[str, Any]]:
    cards_by_digest = {card["features_sha256"]: card for card in run_cards}
    validation_ids = set(split_plan["partitions"][PARTITION]["card_ids"])
    rows: list[dict[str, Any]] = []
    for path in feature_paths:
        feature_rows, digest = _read_features(path)
        card = cards_by_digest[digest]
        if card["card_id"] not in validation_ids:
            continue
        for row in feature_rows:
            if row["feature_status"] != "abstained":
                continue
            rows.append(
                {
                    "card_id": card["card_id"],
                    "sequence": row["sequence"],
                    "input_frame_sha256": row["input_frame_sha256"],
                    "status": "abstained",
                    "score": None,
                    "review_flag": None,
                }
            )
    rows.sort(
        key=lambda item: (item["card_id"], item["sequence"], item["input_frame_sha256"])
    )
    expected = sum(
        entry["abstained_records"] for entry in bundle["partitions"][PARTITION]
    )
    _require(len(rows) == expected, "physical validation abstention count changed")
    return rows


def _build_result(
    evaluation_approval_record: dict[str, Any],
    evaluation_request: dict[str, Any],
    model: dict[str, Any],
    bundle: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
) -> dict[str, Any]:
    _require(
        evaluation_approval_record["validation_scoring_authorized"] is True,
        "MP-069 requires explicit MP-068 validation-scoring authorization",
    )
    _require(
        evaluation_approval_record["test_scoring_authorized"] is False,
        "MP-069 must keep test scoring unauthorized",
    )
    _require(
        evaluation_approval_record["model_refit_authorized"] is False
        and evaluation_approval_record["preprocessing_refit_authorized"] is False
        and evaluation_approval_record["threshold_recalibration_authorized"] is False,
        "MP-069 requires frozen model, preprocessing, and threshold",
    )
    extracted, abstained_count = _validation_rows(
        bundle, split_plan, run_cards, feature_paths
    )
    scored_rows = _result_rows(extracted, model)
    abstained_rows = _abstained_rows(bundle, split_plan, run_cards, feature_paths)
    rows = sorted(
        scored_rows + abstained_rows,
        key=lambda item: (
            item["card_id"],
            item["sequence"],
            item["input_frame_sha256"],
        ),
    )
    threshold = float(model["calibration"]["threshold"])
    flagged = sum(row["review_flag"] is True for row in scored_rows)
    core = {
        "physical_validation_result_version": VALIDATION_RESULT_VERSION,
        "result_kind": RESULT_KIND,
        "partition": PARTITION,
        "model_id": model["model_id"],
        "model_sha256": _sha(model),
        "evaluation_approval_record_id": evaluation_approval_record[
            "evaluation_approval_record_id"
        ],
        "evaluation_approval_record_sha256": _sha(evaluation_approval_record),
        "evaluation_request_id": evaluation_request["request_id"],
        "model_family": model["model_family"],
        "score_direction": model["score_direction"],
        "score_is_failure_probability": False,
        "threshold": threshold,
        "threshold_source": "frozen_mp066_train_empirical_quantile",
        "threshold_comparison": "score > threshold",
        "rows": rows,
        "counts": {
            "validation_rows_total": len(rows),
            "validation_rows_scored": len(scored_rows),
            "validation_rows_abstained": abstained_count,
            "review_flags": flagged,
        },
        "train_rows_consumed": 0,
        "test_rows_consumed": 0,
        "model_refit_performed": False,
        "preprocessing_refit_performed": False,
        "threshold_recalibration_performed": False,
        "diagnosis_performed": False,
        "failure_probability_estimated": False,
        "rul_estimated": False,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "validation_scoring_authorized": True,
        "validation_scoring_completed": True,
        "test_scoring_authorized": False,
        "deployment_authorized": False,
    }
    return {"result_id": "physical-validation-result:" + _sha(core)[:24], **core}


def score_physical_validation(
    evaluation_approval_record: dict[str, Any],
    evaluation_request: dict[str, Any],
    evaluation_decision: dict[str, Any],
    model: dict[str, Any],
    training_approval_record: dict[str, Any],
    training_request: dict[str, Any],
    training_decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Score validation rows only after full MP-068 chain revalidation."""
    validate_evaluation_approval_record(
        evaluation_approval_record,
        evaluation_request,
        evaluation_decision,
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    result = _build_result(
        evaluation_approval_record,
        evaluation_request,
        model,
        bundle,
        split_plan,
        run_cards,
        feature_paths,
    )
    validate_physical_validation_result(
        result,
        evaluation_approval_record,
        evaluation_request,
        evaluation_decision,
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    return result


def validate_physical_validation_result(
    result: Any,
    evaluation_approval_record: dict[str, Any],
    evaluation_request: dict[str, Any],
    evaluation_decision: dict[str, Any],
    model: dict[str, Any],
    training_approval_record: dict[str, Any],
    training_request: dict[str, Any],
    training_decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> None:
    """Recompute a validation-only result and reject broadened claims or stale data."""
    _require(
        type(result) is dict and set(result) == _RESULT_KEYS,
        "physical validation result fields differ from v1 contract",
    )
    _require(
        result["physical_validation_result_version"] == VALIDATION_RESULT_VERSION,
        "unsupported physical validation result version",
    )
    _require(
        result["result_kind"] == RESULT_KIND, "physical validation result kind changed"
    )
    _require(result["partition"] == PARTITION, "MP-069 may score validation only")
    _require(
        type(result["rows"]) is list
        and all(type(row) is dict and set(row) == _ROW_KEYS for row in result["rows"]),
        "physical validation result row fields differ from v1 contract",
    )
    _require(
        result["score_is_failure_probability"] is False,
        "physical validation score cannot become failure probability",
    )
    _require(
        result["validation_scoring_authorized"] is True
        and result["validation_scoring_completed"] is True,
        "physical validation scoring state changed",
    )
    for field in (
        "test_scoring_authorized",
        "redistribution_cleared",
        "deployment_authorized",
        "model_refit_performed",
        "preprocessing_refit_performed",
        "threshold_recalibration_performed",
        "diagnosis_performed",
        "failure_probability_estimated",
        "rul_estimated",
    ):
        _require(result[field] is False, f"MP-069 must keep {field}=false")
    _require(
        result["train_rows_consumed"] == 0 and result["test_rows_consumed"] == 0,
        "MP-069 must not consume train or test rows for scoring",
    )
    validate_evaluation_approval_record(
        evaluation_approval_record,
        evaluation_request,
        evaluation_decision,
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    expected = _build_result(
        evaluation_approval_record,
        evaluation_request,
        model,
        bundle,
        split_plan,
        run_cards,
        feature_paths,
    )
    _require(
        result == expected,
        "physical validation result does not match exact approved model and sources",
    )


def score_files(
    evaluation_approval_record_path: str | Path,
    evaluation_request_path: str | Path,
    evaluation_decision_path: str | Path,
    model_path: str | Path,
    training_approval_record_path: str | Path,
    training_request_path: str | Path,
    training_decision_path: str | Path,
    preregistration_path: str | Path,
    bundle_path: str | Path,
    readiness_path: str | Path,
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    feature_paths: Sequence[str | Path],
    protocol_path: str | Path,
) -> dict[str, Any]:
    evaluation_approval_record = _read_json(
        evaluation_approval_record_path, "physical evaluation approval record"
    )
    evaluation_request = _read_json(
        evaluation_request_path, "physical evaluation approval request"
    )
    evaluation_decision = _read_json(
        evaluation_decision_path, "physical evaluation human decision"
    )
    model = _read_json(model_path, "physical model artifact")
    training_approval_record = _read_json(
        training_approval_record_path, "physical training approval record"
    )
    training_request = _read_json(
        training_request_path, "physical training approval request"
    )
    training_decision = _read_json(
        training_decision_path, "physical training human decision"
    )
    preregistration = _read_json(
        preregistration_path, "physical experiment preregistration"
    )
    bundle = _read_json(bundle_path, "physical experiment bundle")
    readiness = _read_json(readiness_path, "physical readiness assessment")
    split_plan = _read_json(split_path, "physical split plan")
    cards = [_read_json(path, "physical run card") for path in card_paths]
    reviews = [_read_json(path, "physical evidence review") for path in review_paths]
    protocol = _read_json(protocol_path, "physical experiment protocol")
    return score_physical_validation(
        evaluation_approval_record,
        evaluation_request,
        evaluation_decision,
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        cards,
        reviews,
        feature_paths,
        protocol,
    )


def write_physical_validation_result(path: str | Path, result: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "physical validation result output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "physical validation result output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            result,
            stream,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score only the explicitly approved physical validation partition with "
            "the frozen MP-066 model; never score test or refit/recalibrate"
        )
    )
    parser.add_argument("--evaluation-approval-record", required=True)
    parser.add_argument("--evaluation-request", required=True)
    parser.add_argument("--evaluation-decision", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--training-approval-record", required=True)
    parser.add_argument("--training-request", required=True)
    parser.add_argument("--training-decision", required=True)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--readiness", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True)
    parser.add_argument(
        "--out", required=True, help="write-once validation result JSON"
    )
    args = parser.parse_args(argv)
    result = score_files(
        args.evaluation_approval_record,
        args.evaluation_request,
        args.evaluation_decision,
        args.model,
        args.training_approval_record,
        args.training_request,
        args.training_decision,
        args.preregistration,
        args.bundle,
        args.readiness,
        args.split,
        args.cards,
        args.reviews,
        args.features,
        args.protocol,
    )
    write_physical_validation_result(args.out, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
