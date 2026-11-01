"""Build a pending physical validation-scoring approval request (MP-067).

The request is source- and model-bound but grants no scoring permission. It
revalidates the exact MP-066 model and its complete upstream approval/source chain,
then freezes a validation-only evaluation scope for a later explicit human decision.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .physical_dataset import PUBLICATION_STATUS
from .physical_offline_trainer import validate_physical_model
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json

EVALUATION_REQUEST_VERSION = "1.0.0"
APPROVAL_STATE = "pending_explicit_human_approval"
REQUESTED_CAPABILITY = "offline_validation_scoring_only"
REQUESTED_OPERATIONS = [
    "score_validation_partition_with_frozen_model",
    "review_validation_scores_only",
]
_REQUEST_KEYS = frozenset(
    {
        "evaluation_request_version",
        "request_id",
        "model_id",
        "model_sha256",
        "training_approval_record_id",
        "training_approval_record_sha256",
        "training_request_id",
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


def _build_request(
    model: dict[str, Any],
    approval_record: dict[str, Any],
    training_request: dict[str, Any],
    decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    validate_physical_model(
        model,
        approval_record,
        training_request,
        decision,
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
        model["training_completed"] is True,
        "MP-067 requires a completed MP-066 physical model",
    )
    _require(
        model["model_scoring_authorized"] is False,
        "MP-067 requires the MP-066 model to remain unscored and unauthorized",
    )
    _require(
        model["heldout_partitions"]
        == {
            "validation": "untouched_no_fit_no_score",
            "test": "untouched_no_fit_no_score",
        },
        "MP-067 requires untouched MP-066 held-out partitions",
    )
    design = preregistration["experiment_design"]
    _require(
        design["validation_role"] == "review_only_no_fit",
        "MP-067 validation role differs from preregistration",
    )
    _require(
        design["test_role"] == "final_only_no_fit",
        "MP-067 test role differs from preregistration",
    )

    core = {
        "evaluation_request_version": EVALUATION_REQUEST_VERSION,
        "model_id": model["model_id"],
        "model_sha256": _sha(model),
        "training_approval_record_id": approval_record["approval_record_id"],
        "training_approval_record_sha256": _sha(approval_record),
        "training_request_id": training_request["request_id"],
        "preregistration_id": preregistration["preregistration_id"],
        "source_bundle_id": bundle["bundle_id"],
        "split_plan_sha256": split_plan["plan_sha256"],
        "model_family": model["model_family"],
        "requested_capability": REQUESTED_CAPABILITY,
        "requested_operations": list(REQUESTED_OPERATIONS),
        "partition_roles": {
            "train": "frozen_no_refit_no_rescore",
            "validation": "score_with_frozen_model_after_separate_explicit_approval",
            "test": "untouched_no_score",
        },
        "approval_state": APPROVAL_STATE,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_completed": True,
        "validation_scoring_authorized": False,
        "test_scoring_authorized": False,
        "model_refit_authorized": False,
        "preprocessing_refit_authorized": False,
        "threshold_recalibration_authorized": False,
        "diagnosis_authorized": False,
        "failure_probability_authorized": False,
        "rul_authorized": False,
        "deployment_authorized": False,
    }
    request_id = "physical-evaluation-request:" + _sha(core)[:24]
    challenge = {
        "request_id": request_id,
        "model_id": model["model_id"],
        "model_sha256": core["model_sha256"],
        "training_approval_record_sha256": core["training_approval_record_sha256"],
        "requested_capability": REQUESTED_CAPABILITY,
        "requested_operations": core["requested_operations"],
        "partition_roles": core["partition_roles"],
    }
    challenge_sha256 = _sha(challenge)
    approval_phrase = (
        f"APPROVE PHYSICAL VALIDATION SCORING REQUEST {request_id} "
        f"CHALLENGE {challenge_sha256}"
    )
    return {
        "request_id": request_id,
        **core,
        "approval_challenge_sha256": challenge_sha256,
        "approval_phrase": approval_phrase,
    }


def create_evaluation_approval_request(
    model: dict[str, Any],
    approval_record: dict[str, Any],
    training_request: dict[str, Any],
    decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Create a deterministic pending request for validation scoring only."""
    request = _build_request(
        model,
        approval_record,
        training_request,
        decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    validate_evaluation_approval_request(
        request,
        model,
        approval_record,
        training_request,
        decision,
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


def validate_evaluation_approval_request(
    request: Any,
    model: dict[str, Any],
    approval_record: dict[str, Any],
    training_request: dict[str, Any],
    decision: dict[str, Any],
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
        "physical evaluation approval request fields differ from v1 contract",
    )
    _require(
        request["evaluation_request_version"] == EVALUATION_REQUEST_VERSION,
        "unsupported physical evaluation approval request version",
    )
    _require(
        request["approval_state"] == APPROVAL_STATE,
        "MP-067 request must remain pending explicit human approval",
    )
    _require(
        request["requested_capability"] == REQUESTED_CAPABILITY,
        "MP-067 request capability changed",
    )
    _require(
        request["requested_operations"] == REQUESTED_OPERATIONS,
        "MP-067 requested operations changed",
    )
    _require(
        request["publication_status"] == PUBLICATION_STATUS,
        "physical evaluation request publication boundary changed",
    )
    _require(request["training_completed"] is True, "MP-067 training state changed")
    for field in (
        "redistribution_cleared",
        "validation_scoring_authorized",
        "test_scoring_authorized",
        "model_refit_authorized",
        "preprocessing_refit_authorized",
        "threshold_recalibration_authorized",
        "diagnosis_authorized",
        "failure_probability_authorized",
        "rul_authorized",
        "deployment_authorized",
    ):
        _require(request[field] is False, f"MP-067 must keep {field}=false")
    expected = _build_request(
        model,
        approval_record,
        training_request,
        decision,
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
        "physical evaluation approval request does not match exact model and sources",
    )


def request_files(
    model_path: str | Path,
    approval_record_path: str | Path,
    training_request_path: str | Path,
    decision_path: str | Path,
    preregistration_path: str | Path,
    bundle_path: str | Path,
    readiness_path: str | Path,
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    feature_paths: Sequence[str | Path],
    protocol_path: str | Path,
) -> dict[str, Any]:
    model = _read_json(model_path, "physical model artifact")
    approval_record = _read_json(
        approval_record_path, "physical training approval record"
    )
    training_request = _read_json(
        training_request_path, "physical training approval request"
    )
    decision = _read_json(decision_path, "physical training human decision")
    preregistration = _read_json(
        preregistration_path, "physical experiment preregistration"
    )
    bundle = _read_json(bundle_path, "physical experiment bundle")
    readiness = _read_json(readiness_path, "physical readiness assessment")
    split_plan = _read_json(split_path, "physical split plan")
    cards = [_read_json(path, "physical run card") for path in card_paths]
    reviews = [_read_json(path, "physical evidence review") for path in review_paths]
    protocol = _read_json(protocol_path, "physical experiment protocol")
    return create_evaluation_approval_request(
        model,
        approval_record,
        training_request,
        decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        cards,
        reviews,
        feature_paths,
        protocol,
    )


def write_evaluation_approval_request(
    path: str | Path, request: dict[str, Any]
) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "evaluation approval request output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "evaluation approval request output parent must exist and not be a symlink",
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
            "validation scoring; this command performs no scoring"
        )
    )
    parser.add_argument("--model", required=True, help="MP-066 physical model JSON")
    parser.add_argument("--approval-record", required=True, help="MP-065 approval JSON")
    parser.add_argument("--training-request", required=True, help="MP-064 request JSON")
    parser.add_argument(
        "--decision", required=True, help="exact MP-065 training decision JSON"
    )
    parser.add_argument("--preregistration", required=True, help="MP-063 JSON")
    parser.add_argument("--bundle", required=True, help="MP-062 bundle JSON")
    parser.add_argument("--readiness", required=True, help="MP-061 readiness JSON")
    parser.add_argument("--split", required=True, help="MP-059 split plan JSON")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True, help="MP-063 protocol JSON")
    parser.add_argument("--out", required=True, help="write-once evaluation request JSON")
    args = parser.parse_args(argv)
    request = request_files(
        args.model,
        args.approval_record,
        args.training_request,
        args.decision,
        args.preregistration,
        args.bundle,
        args.readiness,
        args.split,
        args.cards,
        args.reviews,
        args.features,
        args.protocol,
    )
    write_evaluation_approval_request(args.out, request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
