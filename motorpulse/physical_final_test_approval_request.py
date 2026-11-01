"""Build a pending physical final-test scoring approval request (MP-070).

The request binds an exact MP-069 validation result and complete approval/source
chain. It grants no test-scoring permission and never reads test rows for scoring.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .physical_dataset import PUBLICATION_STATUS
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json
from .physical_validation_scorer import validate_physical_validation_result

FINAL_TEST_REQUEST_VERSION = "1.0.0"
APPROVAL_STATE = "pending_explicit_human_approval"
REQUESTED_CAPABILITY = "offline_final_test_scoring_only"
REQUESTED_OPERATIONS = [
    "score_test_partition_with_frozen_model",
    "review_final_test_scores_only",
]
_REQUEST_KEYS = frozenset(
    {
        "final_test_request_version",
        "request_id",
        "validation_result_id",
        "validation_result_sha256",
        "evaluation_approval_record_id",
        "evaluation_approval_record_sha256",
        "evaluation_request_id",
        "model_id",
        "model_sha256",
        "preregistration_id",
        "source_bundle_id",
        "split_plan_sha256",
        "model_family",
        "requested_capability",
        "requested_operations",
        "partition_roles",
        "approval_challenge_sha256",
        "approval_phrase",
        "approval_state",
        "publication_status",
        "redistribution_cleared",
        "training_completed",
        "validation_scoring_completed",
        "train_scoring_authorized",
        "validation_rescoring_authorized",
        "test_scoring_authorized",
        "test_scoring_completed",
        "test_rows_consumed",
        "model_refit_authorized",
        "preprocessing_refit_authorized",
        "threshold_recalibration_authorized",
        "diagnosis_authorized",
        "failure_probability_authorized",
        "rul_authorized",
        "deployment_authorized",
    }
)


def _build_request(
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
    validate_physical_validation_result(
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
        validation_result["partition"] == "validation",
        "MP-070 requires an exact MP-069 validation result",
    )
    _require(
        validation_result["validation_scoring_completed"] is True,
        "MP-070 requires completed validation scoring",
    )
    _require(
        validation_result["test_scoring_authorized"] is False
        and validation_result["test_rows_consumed"] == 0,
        "MP-070 requires the test partition to remain untouched",
    )
    design = preregistration["experiment_design"]
    _require(
        design["test_role"] == "final_only_no_fit",
        "MP-070 test role differs from preregistration",
    )

    core = {
        "final_test_request_version": FINAL_TEST_REQUEST_VERSION,
        "validation_result_id": validation_result["result_id"],
        "validation_result_sha256": _sha(validation_result),
        "evaluation_approval_record_id": evaluation_approval_record[
            "evaluation_approval_record_id"
        ],
        "evaluation_approval_record_sha256": _sha(evaluation_approval_record),
        "evaluation_request_id": evaluation_request["request_id"],
        "model_id": model["model_id"],
        "model_sha256": _sha(model),
        "preregistration_id": preregistration["preregistration_id"],
        "source_bundle_id": bundle["bundle_id"],
        "split_plan_sha256": split_plan["plan_sha256"],
        "model_family": model["model_family"],
        "requested_capability": REQUESTED_CAPABILITY,
        "requested_operations": list(REQUESTED_OPERATIONS),
        "partition_roles": {
            "train": "frozen_no_refit_no_rescore",
            "validation": "completed_frozen_no_rescore",
            "test": "score_with_frozen_model_after_separate_explicit_approval",
        },
        "approval_state": APPROVAL_STATE,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_completed": True,
        "validation_scoring_completed": True,
        "train_scoring_authorized": False,
        "validation_rescoring_authorized": False,
        "test_scoring_authorized": False,
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
    request_id = "physical-final-test-request:" + _sha(core)[:24]
    challenge = {
        "request_id": request_id,
        "validation_result_id": validation_result["result_id"],
        "validation_result_sha256": core["validation_result_sha256"],
        "model_id": model["model_id"],
        "model_sha256": core["model_sha256"],
        "requested_capability": REQUESTED_CAPABILITY,
        "requested_operations": core["requested_operations"],
        "partition_roles": core["partition_roles"],
    }
    challenge_sha256 = _sha(challenge)
    approval_phrase = (
        f"APPROVE PHYSICAL FINAL TEST SCORING REQUEST {request_id} "
        f"CHALLENGE {challenge_sha256}"
    )
    return {
        "request_id": request_id,
        **core,
        "approval_challenge_sha256": challenge_sha256,
        "approval_phrase": approval_phrase,
    }


def create_final_test_approval_request(
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
    """Create a deterministic pending request for final-test scoring only."""
    request = _build_request(
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
    return request


def validate_final_test_approval_request(
    request: Any,
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
    """Recompute the pending request and reject broadened or fabricated scope."""
    _require(
        type(request) is dict and set(request) == _REQUEST_KEYS,
        "physical final-test approval request fields differ from v1 contract",
    )
    _require(
        request["final_test_request_version"] == FINAL_TEST_REQUEST_VERSION,
        "unsupported physical final-test approval request version",
    )
    _require(
        request["approval_state"] == APPROVAL_STATE,
        "MP-070 request must remain pending explicit human approval",
    )
    _require(
        request["requested_capability"] == REQUESTED_CAPABILITY,
        "MP-070 request capability changed",
    )
    _require(
        request["requested_operations"] == REQUESTED_OPERATIONS,
        "MP-070 requested operations changed",
    )
    _require(
        request["validation_scoring_completed"] is True,
        "MP-070 validation completion state changed",
    )
    _require(
        request["test_rows_consumed"] == 0,
        "MP-070 request must not consume test rows",
    )
    for field in (
        "redistribution_cleared",
        "train_scoring_authorized",
        "validation_rescoring_authorized",
        "test_scoring_authorized",
        "test_scoring_completed",
        "model_refit_authorized",
        "preprocessing_refit_authorized",
        "threshold_recalibration_authorized",
        "diagnosis_authorized",
        "failure_probability_authorized",
        "rul_authorized",
        "deployment_authorized",
    ):
        _require(request[field] is False, f"MP-070 must keep {field}=false")
    expected = _build_request(
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
        request == expected,
        "physical final-test approval request does not match exact validation result and sources",
    )


def request_files(
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
    validation_result = _read_json(validation_result_path, "physical validation result")
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
    return create_final_test_approval_request(
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
        cards,
        reviews,
        feature_paths,
        protocol,
    )


def write_final_test_approval_request(
    path: str | Path, request: dict[str, Any]
) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "final-test approval request output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "final-test approval request output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            request,
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
            "Create a pending explicit approval request for frozen-model physical "
            "final-test scoring; this command never scores test rows"
        )
    )
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
    parser.add_argument("--out", required=True, help="write-once final-test request JSON")
    args = parser.parse_args(argv)
    request = request_files(
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
    write_final_test_approval_request(args.out, request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
