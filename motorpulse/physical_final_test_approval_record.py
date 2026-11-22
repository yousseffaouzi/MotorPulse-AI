"""Local final-test approval record (MP-071); no test scoring is performed."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from .physical_final_test_approval_request import (
    REQUESTED_CAPABILITY,
    request_files,
    validate_final_test_approval_request,
    write_final_test_approval_request,
)
from .physical_training_approval_record import (
    DECISION_SIGNATURE_ASSURANCE,
    REVIEWER_IDENTITY_ASSURANCE,
    _reviewer_assertion,
    _strict_utc_timestamp,
)
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json

DECISION_VERSION = "1.0.0"
RECORD_VERSION = "1.0.0"
DECISION_ACTION = "approve_final_test_scoring_only"
APPROVAL_STATE = "approved_for_final_test_scoring_only"
_DECISION_KEYS = frozenset(
    {
        "final_test_approval_decision_version",
        "final_test_request_id",
        "final_test_request_sha256",
        "approval_challenge_sha256",
        "decision",
        "human_affirmation",
        "reviewer_assertion",
        "decided_at_utc",
    }
)


def validate_final_test_human_decision(
    decision: Any, request: dict[str, Any]
) -> None:
    """Check an externally supplied decision; this does not authenticate consent."""
    _require(
        type(decision) is dict and set(decision) == _DECISION_KEYS,
        "final-test approval decision fields differ from v1 contract",
    )
    _require(
        decision["final_test_approval_decision_version"] == DECISION_VERSION,
        "unsupported final-test approval decision version",
    )
    _require(
        decision["decision"] == DECISION_ACTION,
        "decision must explicitly approve final-test scoring only",
    )
    _require(
        decision["final_test_request_id"] == request["request_id"],
        "final-test decision request ID does not match",
    )
    _require(
        decision["final_test_request_sha256"] == _sha(request),
        "final-test decision request SHA-256 does not match",
    )
    _require(
        decision["approval_challenge_sha256"] == request["approval_challenge_sha256"],
        "final-test decision challenge does not match",
    )
    _require(
        decision["human_affirmation"] == request["approval_phrase"],
        "decision requires the exact MP-070 approval phrase",
    )
    _reviewer_assertion(decision["reviewer_assertion"])
    _strict_utc_timestamp(decision["decided_at_utc"])


def _build_record(request: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    validate_final_test_human_decision(decision, request)
    core = {
        "final_test_approval_record_version": RECORD_VERSION,
        "final_test_request_id": request["request_id"],
        "final_test_request_sha256": _sha(request),
        "approval_challenge_sha256": request["approval_challenge_sha256"],
        "validation_result_id": request["validation_result_id"],
        "validation_result_sha256": request["validation_result_sha256"],
        "evaluation_approval_record_id": request["evaluation_approval_record_id"],
        "evaluation_approval_record_sha256": request[
            "evaluation_approval_record_sha256"
        ],
        "model_id": request["model_id"],
        "model_sha256": request["model_sha256"],
        "preregistration_id": request["preregistration_id"],
        "source_bundle_id": request["source_bundle_id"],
        "split_plan_sha256": request["split_plan_sha256"],
        "model_family": request["model_family"],
        "approved_capability": REQUESTED_CAPABILITY,
        "approved_operations": list(request["requested_operations"]),
        "partition_roles": dict(request["partition_roles"]),
        "decision_sha256": _sha(decision),
        "decision": DECISION_ACTION,
        "reviewer_assertion": decision["reviewer_assertion"],
        "decided_at_utc": decision["decided_at_utc"],
        "reviewer_identity_assurance": REVIEWER_IDENTITY_ASSURANCE,
        "decision_signature_assurance": DECISION_SIGNATURE_ASSURANCE,
        "approval_state": APPROVAL_STATE,
        "publication_status": request["publication_status"],
        "redistribution_cleared": False,
        "training_completed": True,
        "validation_scoring_completed": True,
        "train_scoring_authorized": False,
        "validation_rescoring_authorized": False,
        "test_scoring_authorized": True,
        "test_scoring_completed": False,
        "test_rows_consumed": 0,
        "model_refit_authorized": False,
        "preprocessing_refit_authorized": False,
        "threshold_recalibration_authorized": False,
        "diagnosis_authorized": False,
        "failure_probability_authorized": False,
        "rul_authorized": False,
        "deployment_authorized": False,
    }
    return {
        "final_test_approval_record_id": "physical-final-test-approval:"
        + _sha(core)[:24],
        **core,
    }


def create_final_test_approval_record(
    request: dict[str, Any],
    decision: dict[str, Any],
    validation_result: dict[str, Any],
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
    """Revalidate the exact upstream chain before deriving local approval."""
    validate_final_test_approval_request(
        request,
        validation_result,
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
    return _build_record(request, decision)


def validate_final_test_approval_record(
    record: Any,
    request: dict[str, Any],
    decision: dict[str, Any],
    validation_result: dict[str, Any],
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
    """Require the original request, decision and all source inputs again."""
    _require(type(record) is dict, "final-test approval record must be an object")
    expected = create_final_test_approval_record(
        request,
        decision,
        validation_result,
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
    _require(
        record == expected and _sha(record) == _sha(expected),
        "final-test approval record does not match exact request and decision",
    )


def approval_files(
    final_test_request_path: str | Path,
    final_test_decision_path: str | Path,
    validation_result_path: str | Path,
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
    request = _read_json(final_test_request_path, "physical final-test request")
    decision = _read_json(final_test_decision_path, "physical final-test decision")
    expected = request_files(
        validation_result_path,
        evaluation_approval_record_path,
        evaluation_request_path,
        evaluation_decision_path,
        model_path,
        training_approval_record_path,
        training_request_path,
        training_decision_path,
        preregistration_path,
        bundle_path,
        readiness_path,
        split_path,
        card_paths,
        review_paths,
        feature_paths,
        protocol_path,
    )
    _require(
        request == expected and _sha(request) == _sha(expected),
        "final-test request does not match exact validation result and sources",
    )
    return _build_record(expected, decision)


def write_final_test_approval_record(path: str | Path, record: dict[str, Any]) -> None:
    # Same exclusive JSON writer and local path safeguards as MP-070.
    write_final_test_approval_request(path, record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Record an explicit approval for frozen-model physical "
            "final-test scoring; this command never scores test rows"
        )
    )
    parser.add_argument("--final-test-request", required=True)
    parser.add_argument("--final-test-decision", required=True)
    parser.add_argument("--validation-result", required=True)
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
        "--out", required=True, help="write-once final-test approval record JSON"
    )
    args = parser.parse_args(argv)
    record = approval_files(
        args.final_test_request,
        args.final_test_decision,
        args.validation_result,
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
    write_final_test_approval_record(args.out, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
