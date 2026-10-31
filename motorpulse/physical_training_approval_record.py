"""Validate an explicit human decision for one exact physical training request (MP-065).

MP-065 can derive a narrow offline-training authorization record from a separately
supplied decision artifact. It does not create the human decision, fit or score a
model, authenticate reviewer identity, deploy anything, or authorize publication.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Sequence

from .physical_training_approval_request import (
    REQUESTED_CAPABILITY,
    _require,
    _sha,
    validate_approval_request,
)
from .physical_training_readiness import _read_json

APPROVAL_DECISION_VERSION = "1.0.0"
APPROVAL_RECORD_VERSION = "1.0.0"
DECISION_ACTION = "approve_offline_training_only"
APPROVAL_STATE = "approved_for_offline_training_only"
REVIEWER_IDENTITY_ASSURANCE = "self_asserted_not_authenticated"
DECISION_SIGNATURE_ASSURANCE = "none"
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_DECISION_KEYS = frozenset(
    {
        "approval_decision_version",
        "request_id",
        "request_sha256",
        "approval_challenge_sha256",
        "decision",
        "human_affirmation",
        "reviewer_assertion",
        "decided_at_utc",
    }
)
_RECORD_KEYS = frozenset(
    {
        "approval_record_version",
        "approval_record_id",
        "request_id",
        "request_sha256",
        "approval_challenge_sha256",
        "preregistration_id",
        "preregistration_sha256",
        "source_bundle_id",
        "source_bundle_sha256",
        "target_mode",
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
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
        "deployment_authorized",
    }
)


def _strict_utc_timestamp(value: Any) -> str:
    _require(
        type(value) is str and _UTC_TIMESTAMP.fullmatch(value) is not None,
        "decided_at_utc must be an explicit UTC timestamp ending in Z",
    )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("decided_at_utc is not a valid calendar timestamp") from exc
    _require(parsed.utcoffset() is not None, "decided_at_utc must include UTC")
    return value


def _reviewer_assertion(value: Any) -> str:
    _require(
        type(value) is str
        and value == value.strip()
        and 1 <= len(value) <= 128
        and all(ord(character) >= 32 and ord(character) != 127 for character in value),
        "reviewer_assertion must be a non-empty 1-128 character identifier",
    )
    return value


def validate_human_decision(decision: Any, request: dict[str, Any]) -> None:
    """Validate a separately authored approval decision against one exact request."""
    _require(
        type(decision) is dict and set(decision) == _DECISION_KEYS,
        "physical training approval decision fields differ from v1 contract",
    )
    _require(
        decision["approval_decision_version"] == APPROVAL_DECISION_VERSION,
        "unsupported physical training approval decision version",
    )
    _require(
        decision["decision"] == DECISION_ACTION,
        "physical training decision must explicitly approve offline training only",
    )
    _require(
        decision["request_id"] == request["request_id"],
        "physical training decision request ID does not match",
    )
    _require(
        decision["request_sha256"] == _sha(request),
        "physical training decision request SHA-256 does not match",
    )
    _require(
        decision["approval_challenge_sha256"] == request["approval_challenge_sha256"],
        "physical training decision challenge does not match",
    )
    _require(
        decision["human_affirmation"] == request["approval_phrase"],
        "physical training decision requires the exact MP-064 approval phrase",
    )
    _reviewer_assertion(decision["reviewer_assertion"])
    _strict_utc_timestamp(decision["decided_at_utc"])


def _build_record(request: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    validate_human_decision(decision, request)
    core = {
        "approval_record_version": APPROVAL_RECORD_VERSION,
        "request_id": request["request_id"],
        "request_sha256": _sha(request),
        "approval_challenge_sha256": request["approval_challenge_sha256"],
        "preregistration_id": request["preregistration_id"],
        "preregistration_sha256": request["preregistration_sha256"],
        "source_bundle_id": request["source_bundle_id"],
        "source_bundle_sha256": request["source_bundle_sha256"],
        "target_mode": request["target_mode"],
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
        "training_authorized": True,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
        "deployment_authorized": False,
    }
    return {
        "approval_record_id": "physical-training-approval:" + _sha(core)[:24],
        **core,
    }


def create_approval_record(
    request: dict[str, Any],
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
    """Create a narrow record only after exact request and decision revalidation."""
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
    record = _build_record(request, decision)
    validate_approval_record(
        record,
        request,
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
    return record


def validate_approval_record(
    record: Any,
    request: dict[str, Any],
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
    """Revalidate the full source chain and reject broadened approval records."""
    _require(
        type(record) is dict and set(record) == _RECORD_KEYS,
        "physical training approval record fields differ from v1 contract",
    )
    _require(
        record["approval_record_version"] == APPROVAL_RECORD_VERSION,
        "unsupported physical training approval record version",
    )
    _require(
        record["approval_state"] == APPROVAL_STATE,
        "physical training approval state changed",
    )
    _require(
        record["approved_capability"] == REQUESTED_CAPABILITY,
        "physical training approval capability changed",
    )
    _require(
        record["reviewer_identity_assurance"] == REVIEWER_IDENTITY_ASSURANCE,
        "physical training reviewer identity assurance changed",
    )
    _require(
        record["decision_signature_assurance"] == DECISION_SIGNATURE_ASSURANCE,
        "physical training decision signature assurance changed",
    )
    _require(
        record["training_authorized"] is True,
        "MP-065 approval record must authorize only the exact offline training scope",
    )
    for field in (
        "redistribution_cleared",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
        "deployment_authorized",
    ):
        _require(record[field] is False, f"MP-065 must keep {field}=false")
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
    validate_human_decision(decision, request)
    expected = _build_record(request, decision)
    _require(
        record == expected,
        "physical training approval record does not match exact request and decision",
    )


def approval_files(
    request_path: str | Path,
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
    request = _read_json(request_path, "physical training approval request")
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
    return create_approval_record(
        request,
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


def write_approval_record(path: str | Path, record: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "approval record output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "approval record output parent must exist and not be a symlink",
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
            "Validate a separately authored human decision and record exact offline "
            "physical training approval"
        )
    )
    parser.add_argument("--request", required=True, help="MP-064 approval request JSON")
    parser.add_argument(
        "--decision", required=True, help="separately authored human decision JSON"
    )
    parser.add_argument("--preregistration", required=True, help="MP-063 JSON")
    parser.add_argument("--bundle", required=True, help="MP-062 bundle JSON")
    parser.add_argument("--readiness", required=True, help="MP-061 readiness JSON")
    parser.add_argument("--split", required=True, help="MP-059 split plan JSON")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True, help="MP-063 protocol JSON")
    parser.add_argument("--out", required=True, help="write-once approval record JSON")
    args = parser.parse_args(argv)
    record = approval_files(
        args.request,
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
    write_approval_record(args.out, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
