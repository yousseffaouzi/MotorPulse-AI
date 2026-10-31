"""Build an explicit human-approval request without granting approval (MP-064)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .physical_dataset import PUBLICATION_STATUS
from .physical_experiment_preregistration import validate_preregistration
from .physical_training_readiness import _read_json

APPROVAL_REQUEST_VERSION = "1.0.0"
APPROVAL_STATE = "pending_explicit_human_approval"
REQUESTED_CAPABILITY = "offline_training_only"
_REQUEST_KEYS = frozenset(
    {
        "approval_request_version",
        "request_id",
        "preregistration_id",
        "preregistration_sha256",
        "source_bundle_id",
        "source_bundle_sha256",
        "target_mode",
        "model_family",
        "requested_capability",
        "requested_operations",
        "partition_roles",
        "approval_challenge_sha256",
        "approval_phrase",
        "approval_state",
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


def _build_request(
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
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
    _require(
        preregistration["authorization_state"]
        == "eligible_for_explicit_training_approval",
        "MP-064 requires an MP-063 preregistration eligible for explicit training approval",
    )
    _require(
        preregistration["blockers"] == [],
        "MP-064 requires an MP-063 preregistration with no blockers",
    )
    design = preregistration["experiment_design"]
    core = {
        "approval_request_version": APPROVAL_REQUEST_VERSION,
        "preregistration_id": preregistration["preregistration_id"],
        "preregistration_sha256": _sha(preregistration),
        "source_bundle_id": preregistration["source_bundle_id"],
        "source_bundle_sha256": preregistration["source_bundle_sha256"],
        "target_mode": preregistration["target_mode"],
        "model_family": design["model_family"],
        "requested_capability": REQUESTED_CAPABILITY,
        "requested_operations": [
            "fit_preprocessing_on_train",
            "fit_model_on_train",
            "derive_threshold_on_train",
        ],
        "partition_roles": {
            "fit_partition": design["fit_partition"],
            "preprocessing_fit_partition": design["preprocessing_fit_partition"],
            "threshold_partition": design["threshold_partition"],
            "validation_role": design["validation_role"],
            "test_role": design["test_role"],
        },
        "approval_state": APPROVAL_STATE,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    request_id = "physical-training-request:" + _sha(core)[:24]
    challenge = {
        "request_id": request_id,
        "preregistration_id": preregistration["preregistration_id"],
        "preregistration_sha256": core["preregistration_sha256"],
        "source_bundle_sha256": core["source_bundle_sha256"],
        "requested_capability": REQUESTED_CAPABILITY,
        "requested_operations": core["requested_operations"],
    }
    challenge_sha256 = _sha(challenge)
    approval_phrase = (
        f"APPROVE OFFLINE TRAINING REQUEST {request_id} CHALLENGE {challenge_sha256}"
    )
    return {
        "request_id": request_id,
        **core,
        "approval_challenge_sha256": challenge_sha256,
        "approval_phrase": approval_phrase,
    }


def create_approval_request(
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Create a deterministic pending request for exact offline-training scope."""
    request = _build_request(
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    validate_approval_request(
        request,
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


def validate_approval_request(
    request: Any,
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> None:
    """Recompute a request and reject broadened scope or fabricated approval."""
    _require(
        type(request) is dict and set(request) == _REQUEST_KEYS,
        "physical training approval request fields differ from v1 contract",
    )
    _require(
        request["approval_request_version"] == APPROVAL_REQUEST_VERSION,
        "unsupported physical training approval request version",
    )
    _require(
        request["approval_state"] == APPROVAL_STATE,
        "MP-064 request must remain pending explicit human approval",
    )
    _require(
        request["requested_capability"] == REQUESTED_CAPABILITY,
        "MP-064 request capability changed",
    )
    _require(
        request["publication_status"] == PUBLICATION_STATUS,
        "physical training approval request publication boundary changed",
    )
    for field in (
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    ):
        _require(request[field] is False, f"MP-064 must keep {field}=false")
    expected = _build_request(
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
        "physical training approval request does not match exact sources and scope",
    )


def request_files(
    preregistration_path: str | Path,
    bundle_path: str | Path,
    readiness_path: str | Path,
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    feature_paths: Sequence[str | Path],
    protocol_path: str | Path,
) -> dict[str, Any]:
    preregistration = _read_json(
        preregistration_path, "physical experiment preregistration"
    )
    bundle = _read_json(bundle_path, "physical experiment bundle")
    readiness = _read_json(readiness_path, "physical readiness assessment")
    split_plan = _read_json(split_path, "physical split plan")
    cards = [_read_json(path, "physical run card") for path in card_paths]
    reviews = [_read_json(path, "physical evidence review") for path in review_paths]
    protocol = _read_json(protocol_path, "physical experiment protocol")
    return create_approval_request(
        preregistration,
        bundle,
        readiness,
        split_plan,
        cards,
        reviews,
        feature_paths,
        protocol,
    )


def write_approval_request(path: str | Path, request: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "approval request output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "approval request output parent must exist and not be a symlink",
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
        description="Create a pending human approval request for exact offline training"
    )
    parser.add_argument("--preregistration", required=True, help="MP-063 JSON")
    parser.add_argument("--bundle", required=True, help="MP-062 bundle JSON")
    parser.add_argument("--readiness", required=True, help="MP-061 readiness JSON")
    parser.add_argument("--split", required=True, help="MP-059 split plan JSON")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True, help="MP-063 protocol JSON")
    parser.add_argument("--out", required=True, help="write-once approval request JSON")
    args = parser.parse_args(argv)
    request = request_files(
        args.preregistration,
        args.bundle,
        args.readiness,
        args.split,
        args.cards,
        args.reviews,
        args.features,
        args.protocol,
    )
    write_approval_request(args.out, request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
