"""Record an explicit human decision for physical validation scoring (MP-068).

MP-068 can derive a narrow validation-scoring authorization record from a
separately supplied decision artifact. It does not score a physical row, refit a
model, recalibrate a threshold, authenticate reviewer identity, or deploy anything.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .physical_evaluation_approval_request import (
    REQUESTED_CAPABILITY,
    validate_evaluation_approval_request,
)
from .physical_training_approval_record import (
    DECISION_SIGNATURE_ASSURANCE,
    REVIEWER_IDENTITY_ASSURANCE,
    _reviewer_assertion,
    _strict_utc_timestamp,
)
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json

EVALUATION_APPROVAL_DECISION_VERSION = "1.0.0"
EVALUATION_APPROVAL_RECORD_VERSION = "1.0.0"
DECISION_ACTION = "approve_validation_scoring_only"
APPROVAL_STATE = "approved_for_validation_scoring_only"
_DECISION_KEYS = frozenset(
    {
        "evaluation_approval_decision_version",
        "evaluation_request_id",
        "evaluation_request_sha256",
        "approval_challenge_sha256",
        "decision",
        "human_affirmation",
        "reviewer_assertion",
        "decided_at_utc",
    }
)
_RECORD_KEYS = frozenset(
    {
        "evaluation_approval_record_version",
        "evaluation_approval_record_id",
        "evaluation_request_id",
        "evaluation_request_sha256",
        "approval_challenge_sha256",
        "model_id",
        "model_sha256",
        "training_approval_record_id",
        "training_approval_record_sha256",
        "preregistration_id",
        "source_bundle_id",
        "split_plan_sha256",
        "model_family",
        "approved_capability",
        "approved_operations",
        "partition_roles",
        "decision_sha256",
        "decision",
        "reviewer_assertion",
        "decided_at_utc",
        "reviewer_identity_assurance",
        "decision_signature_assurance",
        "approval_state",
        "publication_status",
        "redistribution_cleared",
        "training_completed",
        "train_scoring_authorized",
        "validation_scoring_authorized",
        "test_scoring_authorized",
        "model_refit_authorized",
        "preprocessing_refit_authorized",
        "threshold_recalibration_authorized",
        "diagnosis_authorized",
        "failure_probability_authorized",
        "rul_authorized",
        "deployment_authorized",
    }
)


def validate_evaluation_human_decision(decision: Any, request: dict[str, Any]) -> None:
    """Validate a separately authored decision against one exact MP-067 request."""
    _require(
        type(decision) is dict and set(decision) == _DECISION_KEYS,
        "physical evaluation approval decision fields differ from v1 contract",
    )
    _require(
        decision["evaluation_approval_decision_version"]
        == EVALUATION_APPROVAL_DECISION_VERSION,
        "unsupported physical evaluation approval decision version",
    )
    _require(
        decision["decision"] == DECISION_ACTION,
        "physical evaluation decision must explicitly approve validation scoring only",
    )
    _require(
        decision["evaluation_request_id"] == request["request_id"],
        "physical evaluation decision request ID does not match",
    )
    _require(
        decision["evaluation_request_sha256"] == _sha(request),
        "physical evaluation decision request SHA-256 does not match",
    )
    _require(
        decision["approval_challenge_sha256"] == request["approval_challenge_sha256"],
        "physical evaluation decision challenge does not match",
    )
    _require(
        decision["human_affirmation"] == request["approval_phrase"],
        "physical evaluation decision requires the exact MP-067 approval phrase",
    )
    _reviewer_assertion(decision["reviewer_assertion"])
    _strict_utc_timestamp(decision["decided_at_utc"])


def _build_record(request: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    validate_evaluation_human_decision(decision, request)
    core = {
        "evaluation_approval_record_version": EVALUATION_APPROVAL_RECORD_VERSION,
        "evaluation_request_id": request["request_id"],
        "evaluation_request_sha256": _sha(request),
        "approval_challenge_sha256": request["approval_challenge_sha256"],
        "model_id": request["model_id"],
        "model_sha256": request["model_sha256"],
        "training_approval_record_id": request["training_approval_record_id"],
        "training_approval_record_sha256": request["training_approval_record_sha256"],
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
        "train_scoring_authorized": False,
        "validation_scoring_authorized": True,
        "test_scoring_authorized": False,
        "model_refit_authorized": False,
        "preprocessing_refit_authorized": False,
        "threshold_recalibration_authorized": False,
        "diagnosis_authorized": False,
        "failure_probability_authorized": False,
        "rul_authorized": False,
        "deployment_authorized": False,
    }
    return {
        "evaluation_approval_record_id": "physical-evaluation-approval:"
        + _sha(core)[:24],
        **core,
    }


def create_evaluation_approval_record(
    request: dict[str, Any],
    decision: dict[str, Any],
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
    """Create a narrow validation-scoring record after full-chain revalidation."""
    validate_evaluation_approval_request(
        request,
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
    record = _build_record(request, decision)
    validate_evaluation_approval_record(
        record,
        request,
        decision,
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
    return record


def validate_evaluation_approval_record(
    record: Any,
    request: dict[str, Any],
    decision: dict[str, Any],
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
    """Revalidate every source and reject broadened evaluation authorization."""
    _require(
        type(record) is dict and set(record) == _RECORD_KEYS,
        "physical evaluation approval record fields differ from v1 contract",
    )
    _require(
        record["evaluation_approval_record_version"]
        == EVALUATION_APPROVAL_RECORD_VERSION,
        "unsupported physical evaluation approval record version",
    )
    _require(
        record["approval_state"] == APPROVAL_STATE,
        "physical evaluation approval state changed",
    )
    _require(
        record["approved_capability"] == REQUESTED_CAPABILITY,
        "physical evaluation approval capability changed",
    )
    _require(
        record["reviewer_identity_assurance"] == REVIEWER_IDENTITY_ASSURANCE,
        "physical evaluation reviewer identity assurance changed",
    )
    _require(
        record["decision_signature_assurance"] == DECISION_SIGNATURE_ASSURANCE,
        "physical evaluation decision signature assurance changed",
    )
    _require(
        record["training_completed"] is True,
        "MP-068 requires the already completed MP-066 training step",
    )
    _require(
        record["validation_scoring_authorized"] is True,
        "MP-068 record must authorize only exact validation scoring",
    )
    for field in (
        "redistribution_cleared",
        "train_scoring_authorized",
        "test_scoring_authorized",
        "model_refit_authorized",
        "preprocessing_refit_authorized",
        "threshold_recalibration_authorized",
        "diagnosis_authorized",
        "failure_probability_authorized",
        "rul_authorized",
        "deployment_authorized",
    ):
        _require(record[field] is False, f"MP-068 must keep {field}=false")
    validate_evaluation_approval_request(
        request,
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
    validate_evaluation_human_decision(decision, request)
    expected = _build_record(request, decision)
    _require(
        record == expected,
        "physical evaluation approval record does not match exact request and decision",
    )


def approval_files(
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
    request = _read_json(
        evaluation_request_path, "physical evaluation approval request"
    )
    decision = _read_json(
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
    return create_evaluation_approval_record(
        request,
        decision,
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


def write_evaluation_approval_record(path: str | Path, record: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "evaluation approval record output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "evaluation approval record output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            record,
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
            "Validate a separately authored human decision and record exact frozen-model "
            "physical validation-scoring approval; this command performs no scoring"
        )
    )
    parser.add_argument(
        "--evaluation-request", required=True, help="MP-067 request JSON"
    )
    parser.add_argument(
        "--evaluation-decision",
        required=True,
        help="separately authored validation-scoring human decision JSON",
    )
    parser.add_argument("--model", required=True, help="MP-066 physical model JSON")
    parser.add_argument(
        "--training-approval-record", required=True, help="MP-065 approval JSON"
    )
    parser.add_argument("--training-request", required=True, help="MP-064 request JSON")
    parser.add_argument(
        "--training-decision", required=True, help="exact MP-065 training decision JSON"
    )
    parser.add_argument("--preregistration", required=True, help="MP-063 JSON")
    parser.add_argument("--bundle", required=True, help="MP-062 bundle JSON")
    parser.add_argument("--readiness", required=True, help="MP-061 readiness JSON")
    parser.add_argument("--split", required=True, help="MP-059 split plan JSON")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True, help="MP-063 protocol JSON")
    parser.add_argument(
        "--out", required=True, help="write-once evaluation approval record JSON"
    )
    args = parser.parse_args(argv)
    record = approval_files(
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
    write_evaluation_approval_record(args.out, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
