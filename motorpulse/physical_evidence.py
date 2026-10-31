"""Local-only physical calibration and evidence review protocol (MP-060).

The review manifest records evidence metadata without embedding evidence files.
It cannot authorize physical model training/scoring, diagnosis, RUL, data
redistribution, live hardware connectivity, or control-system integration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .physical_dataset import PUBLICATION_STATUS, validate_run_card

REVIEW_VERSION = "1.0.0"
MAX_JSON_BYTES = 262_144
MAX_TEXT = 128
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SECTION_NAMES = ("calibration", "label_failure", "rights_privacy")
_SECTION_KEYS = frozenset({"review_status", "evidence"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_id",
        "evidence_sha256",
        "evidence_date_utc",
        "expires_at_utc",
        "origin",
        "kind",
    }
)
_REQUEST_KEYS = frozenset(
    {
        "review_version",
        "reviewer_id",
        "reviewed_at_utc",
        "calibration",
        "label_failure",
        "rights_privacy",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "review_version",
        "review_id",
        "run_card_id",
        "run_card_sha256",
        "reviewer_id",
        "reviewed_at_utc",
        "categories",
        "publication_status",
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    }
)
_ALLOWED_KINDS = {
    "calibration": frozenset(
        {
            "calibration_certificate",
            "reference_instrument_record",
            "calibration_procedure_record",
        }
    ),
    "label_failure": frozenset(
        {
            "maintenance_record",
            "inspection_record",
            "controlled_test_record",
            "observed_failure_record",
        }
    ),
    "rights_privacy": frozenset(
        {
            "ownership_record",
            "permission_record",
            "consent_record",
            "privacy_review",
        }
    ),
}
_ALLOWED_ORIGINS = {
    "calibration": frozenset({"external_record", "independent_measurement"}),
    "label_failure": frozenset(
        {"external_record", "independent_observation", "controlled_test"}
    ),
    "rights_privacy": frozenset({"external_record", "owner_documentation"}),
}


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


def _text(value: Any, field: str) -> str:
    _require(
        type(value) is str and 0 < len(value) <= MAX_TEXT,
        f"{field} must be 1-{MAX_TEXT} characters",
    )
    _require(
        not any(ord(char) < 32 for char in value),
        f"{field} contains control characters",
    )
    return value


def _digest(value: Any, field: str) -> str:
    _require(
        type(value) is str and _SHA256.fullmatch(value) is not None,
        f"{field} must be lowercase SHA-256",
    )
    return value


def _utc(value: Any, field: str) -> datetime:
    _require(type(value) is str, f"{field} must be a UTC ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO 8601") from exc
    _require(
        parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0),
        f"{field} must use UTC",
    )
    return parsed


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
    _require(
        0 < size <= MAX_JSON_BYTES,
        f"{field} file size is empty or exceeds the limit",
    )
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8") from exc
    return _strict_json(text, field)


def _validate_evidence(
    section_name: str,
    evidence: Any,
    reviewed_at: datetime,
) -> dict[str, Any]:
    _require(
        type(evidence) is dict and set(evidence) == _EVIDENCE_KEYS,
        f"{section_name} evidence fields differ from v1 contract",
    )
    evidence_id = _text(evidence["evidence_id"], f"{section_name}.evidence_id")
    evidence_sha256 = _digest(
        evidence["evidence_sha256"], f"{section_name}.evidence_sha256"
    )
    evidence_date = _utc(
        evidence["evidence_date_utc"], f"{section_name}.evidence_date_utc"
    )
    _require(
        evidence_date <= reviewed_at,
        f"{section_name} evidence cannot post-date the review",
    )
    expires_value = evidence["expires_at_utc"]
    expires_at: datetime | None = None
    if expires_value is not None:
        expires_at = _utc(expires_value, f"{section_name}.expires_at_utc")
        _require(
            expires_at > evidence_date,
            f"{section_name} evidence expiry must follow its evidence date",
        )
        _require(
            expires_at > reviewed_at,
            f"{section_name} evidence is expired at review time",
        )
    origin = _text(evidence["origin"], f"{section_name}.origin")
    _require(
        origin in _ALLOWED_ORIGINS[section_name],
        f"{section_name} evidence origin is not independently acceptable",
    )
    kind = _text(evidence["kind"], f"{section_name}.kind")
    _require(
        kind in _ALLOWED_KINDS[section_name],
        f"{section_name} evidence kind is not allowed",
    )
    return {
        "evidence_id": evidence_id,
        "evidence_sha256": evidence_sha256,
        "evidence_date_utc": evidence["evidence_date_utc"],
        "expires_at_utc": evidence["expires_at_utc"],
        "origin": origin,
        "kind": kind,
    }


def _validate_section(
    name: str,
    section: Any,
    reviewed_at: datetime,
) -> dict[str, Any]:
    _require(
        type(section) is dict and set(section) == _SECTION_KEYS,
        f"{name} review fields differ from v1 contract",
    )
    status = section["review_status"]
    _require(
        status in ("reviewed", "not_reviewed"),
        f"{name}.review_status must be reviewed or not_reviewed",
    )
    raw_evidence = section["evidence"]
    _require(type(raw_evidence) is list, f"{name}.evidence must be a list")
    if status == "reviewed":
        _require(raw_evidence, f"{name} reviewed status requires evidence")
    else:
        _require(
            not raw_evidence,
            f"{name} not_reviewed status cannot carry evidence",
        )
    evidence = [
        _validate_evidence(name, item, reviewed_at) for item in raw_evidence
    ]
    ids = [item["evidence_id"] for item in evidence]
    _require(
        len(ids) == len(set(ids)),
        f"{name} evidence IDs must be unique within the category",
    )
    return {
        "review_status": status,
        "evidence_count": len(evidence),
        "evidence": evidence,
    }


def validate_review_request(request: Any) -> dict[str, Any]:
    """Validate local evidence metadata without promoting any authorization."""
    _require(
        type(request) is dict and set(request) == _REQUEST_KEYS,
        "physical evidence review request fields differ from v1 contract",
    )
    _require(
        request["review_version"] == REVIEW_VERSION,
        "unsupported physical evidence review version",
    )
    reviewer_id = _text(request["reviewer_id"], "reviewer_id")
    reviewed_at = _utc(request["reviewed_at_utc"], "reviewed_at_utc")
    categories = {
        name: _validate_section(name, request[name], reviewed_at)
        for name in _SECTION_NAMES
    }
    return {
        "review_version": REVIEW_VERSION,
        "reviewer_id": reviewer_id,
        "reviewed_at_utc": request["reviewed_at_utc"],
        "categories": categories,
    }


def create_review_manifest(
    run_card: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    """Create a deterministic, source-bound evidence review manifest."""
    validate_run_card(run_card)
    normalized = validate_review_request(request)
    run_card_sha256 = _sha(run_card)
    body = {
        "review_version": REVIEW_VERSION,
        "run_card_id": run_card["card_id"],
        "run_card_sha256": run_card_sha256,
        "reviewer_id": normalized["reviewer_id"],
        "reviewed_at_utc": normalized["reviewed_at_utc"],
        "categories": normalized["categories"],
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    manifest = {"review_id": "physical-review:" + _sha(body)[:24], **body}
    validate_review_manifest(manifest, run_card)
    return manifest


def validate_review_manifest(manifest: Any, run_card: dict[str, Any]) -> None:
    """Verify manifest integrity and its immutable authorization boundary."""
    validate_run_card(run_card)
    _require(
        type(manifest) is dict and set(manifest) == _MANIFEST_KEYS,
        "physical evidence review manifest fields differ from v1 contract",
    )
    _require(
        manifest["review_version"] == REVIEW_VERSION,
        "unsupported physical evidence review manifest version",
    )
    _require(
        manifest["run_card_id"] == run_card["card_id"],
        "physical evidence review is bound to a different run card",
    )
    expected_card_sha = _sha(run_card)
    _require(
        manifest["run_card_sha256"] == expected_card_sha,
        "physical evidence review run-card hash mismatch",
    )
    _text(manifest["reviewer_id"], "reviewer_id")
    reviewed_at = _utc(manifest["reviewed_at_utc"], "reviewed_at_utc")
    categories = manifest["categories"]
    _require(
        type(categories) is dict and set(categories) == set(_SECTION_NAMES),
        "physical evidence review categories differ from v1 contract",
    )
    normalized_categories = {
        name: _validate_section(
            name,
            {
                "review_status": categories[name]["review_status"],
                "evidence": categories[name]["evidence"],
            },
            reviewed_at,
        )
        for name in _SECTION_NAMES
    }
    _require(
        categories == normalized_categories,
        "physical evidence review category summary is inconsistent",
    )
    _require(
        manifest["publication_status"] == PUBLICATION_STATUS,
        "physical evidence review publication boundary changed",
    )
    for field in (
        "redistribution_cleared",
        "training_authorized",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "rul_authorized",
    ):
        _require(
            manifest[field] is False,
            f"MP-060 must keep {field}=false",
        )
    body = {key: value for key, value in manifest.items() if key != "review_id"}
    _require(
        manifest["review_id"] == "physical-review:" + _sha(body)[:24],
        "physical evidence review ID does not match canonical content",
    )


def review_files(
    run_card_path: str | Path,
    request_path: str | Path,
) -> dict[str, Any]:
    run_card = _read_json(run_card_path, "physical run card")
    request = _read_json(request_path, "physical evidence review request")
    return create_review_manifest(run_card, request)


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "review output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "review output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            manifest,
            stream,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review local physical evidence metadata without authorizing training"
    )
    parser.add_argument("--card", required=True, help="MP-059 physical run card")
    parser.add_argument(
        "--request", required=True, help="local physical evidence review request JSON"
    )
    parser.add_argument("--out", required=True, help="write-once review manifest JSON")
    args = parser.parse_args(argv)
    manifest = review_files(args.card, args.request)
    write_manifest(args.out, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
