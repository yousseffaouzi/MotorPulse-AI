from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_evidence import (
    create_review_manifest,
    main,
    review_files,
    validate_review_manifest,
    validate_review_request,
)


def _sha(value: object) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _card(*, session_id: str = "session-a", asset_id: str = "PHYS-MTR-A") -> dict:
    body = {
        "card_version": "1.0.0",
        "dataset_type": "user_supplied_local_physical_features",
        "session_id": session_id,
        "asset_id": asset_id,
        "device_id": "esp32-lab-01",
        "feature_version": "1.0.0",
        "records": 10,
        "extracted_records": 9,
        "abstained_records": 1,
        "captured_start_utc": "2026-10-30T10:00:00Z",
        "captured_end_utc": "2026-10-30T10:00:09Z",
        "sampling_contracts": [{"sample_rate_hz": 1024, "sample_count": 1024}],
        "sensor_provenance": {
            "device_family": "esp32",
            "firmware_version": "0.1.0",
            "accelerometer_model": "lab-accelerometer",
            "temperature_sensor_model": "lab-temperature",
            "rpm_sensor_model": "lab-tachometer",
        },
        "features_sha256": "1" * 64,
        "canonical_frames_sha256": "2" * 64,
        "input_capture_sha256": "3" * 64,
        "calibration_status": "unverified",
        "label_status": "unknown",
        "failure_evidence_status": "unknown",
        "publication_status": "local_only_do_not_redistribute",
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    return {"card_id": "physical-run:" + _sha(body)[:24], **body}


def _evidence(
    *,
    evidence_id: str,
    digest_char: str,
    kind: str,
    origin: str,
    date: str = "2026-10-01T00:00:00Z",
    expiry: str | None = None,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_sha256": digest_char * 64,
        "evidence_date_utc": date,
        "expires_at_utc": expiry,
        "origin": origin,
        "kind": kind,
    }


def _request() -> dict:
    return {
        "review_version": "1.0.0",
        "reviewer_id": "lab-reviewer-01",
        "reviewed_at_utc": "2026-10-31T00:00:00Z",
        "calibration": {
            "review_status": "reviewed",
            "evidence": [
                _evidence(
                    evidence_id="cal-cert-001",
                    digest_char="a",
                    kind="calibration_certificate",
                    origin="external_record",
                    expiry="2027-10-01T00:00:00Z",
                )
            ],
        },
        "label_failure": {"review_status": "not_reviewed", "evidence": []},
        "rights_privacy": {
            "review_status": "reviewed",
            "evidence": [
                _evidence(
                    evidence_id="owner-record-001",
                    digest_char="b",
                    kind="ownership_record",
                    origin="owner_documentation",
                )
            ],
        },
    }


class PhysicalEvidenceRequestTests(unittest.TestCase):
    def test_categories_are_independent_and_never_authorize_training(self):
        card = _card()
        manifest = create_review_manifest(card, _request())
        self.assertEqual(
            manifest["categories"]["calibration"]["review_status"], "reviewed"
        )
        self.assertEqual(
            manifest["categories"]["label_failure"]["review_status"], "not_reviewed"
        )
        self.assertEqual(
            manifest["categories"]["rights_privacy"]["review_status"], "reviewed"
        )
        self.assertEqual(manifest["categories"]["calibration"]["evidence_count"], 1)
        self.assertEqual(manifest["categories"]["label_failure"]["evidence_count"], 0)
        self.assertFalse(manifest["redistribution_cleared"])
        self.assertFalse(manifest["training_authorized"])
        self.assertFalse(manifest["model_scoring_authorized"])
        self.assertFalse(manifest["diagnosis_authorized"])
        self.assertFalse(manifest["rul_authorized"])
        validate_review_manifest(manifest, card)

    def test_signal_inference_cannot_be_used_as_physical_label_evidence(self):
        request = _request()
        request["label_failure"] = {
            "review_status": "reviewed",
            "evidence": [
                _evidence(
                    evidence_id="signal-label-001",
                    digest_char="c",
                    kind="inspection_record",
                    origin="signal_inference",
                )
            ],
        }
        with self.assertRaisesRegex(
            ValueError, "origin is not independently acceptable"
        ):
            validate_review_request(request)

    def test_expired_or_future_evidence_fails_closed(self):
        expired = _request()
        expired["calibration"]["evidence"][0]["expires_at_utc"] = "2026-10-15T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "expired at review time"):
            validate_review_request(expired)

        future = _request()
        future["rights_privacy"]["evidence"][0]["evidence_date_utc"] = (
            "2026-11-01T00:00:00Z"
        )
        with self.assertRaisesRegex(ValueError, "cannot post-date the review"):
            validate_review_request(future)

    def test_not_reviewed_section_cannot_smuggle_evidence(self):
        request = _request()
        request["label_failure"]["evidence"] = [
            _evidence(
                evidence_id="hidden-label-001",
                digest_char="d",
                kind="inspection_record",
                origin="external_record",
            )
        ]
        with self.assertRaisesRegex(
            ValueError, "not_reviewed status cannot carry evidence"
        ):
            validate_review_request(request)


class PhysicalEvidenceManifestTests(unittest.TestCase):
    def test_review_is_bound_to_exact_run_card(self):
        card = _card()
        manifest = create_review_manifest(card, _request())
        other = _card(session_id="session-b")
        with self.assertRaisesRegex(ValueError, "bound to a different run card"):
            validate_review_manifest(manifest, other)

    def test_authorization_flags_cannot_be_promoted_by_editing_manifest(self):
        card = _card()
        manifest = create_review_manifest(card, _request())
        for field in (
            "redistribution_cleared",
            "training_authorized",
            "model_scoring_authorized",
            "diagnosis_authorized",
            "rul_authorized",
        ):
            forged = deepcopy(manifest)
            forged[field] = True
            with self.assertRaisesRegex(ValueError, f"keep {field}=false"):
                validate_review_manifest(forged, card)

    def test_review_id_changes_with_evidence_metadata(self):
        card = _card()
        first = create_review_manifest(card, _request())
        changed = _request()
        changed["calibration"]["evidence"][0]["evidence_sha256"] = "e" * 64
        second = create_review_manifest(card, changed)
        self.assertNotEqual(first["review_id"], second["review_id"])
        self.assertEqual(first["run_card_sha256"], second["run_card_sha256"])

    def test_cli_is_strict_and_write_once(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            card_path = root / "card.json"
            request_path = root / "request.json"
            output = root / "review.json"
            card_path.write_text(json.dumps(_card()), encoding="utf-8")
            request_path.write_text(json.dumps(_request()), encoding="utf-8")
            self.assertEqual(
                main(
                    [
                        "--card",
                        str(card_path),
                        "--request",
                        str(request_path),
                        "--out",
                        str(output),
                    ]
                ),
                0,
            )
            manifest = json.loads(output.read_text(encoding="utf-8"))
            validate_review_manifest(manifest, _card())
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(
                    [
                        "--card",
                        str(card_path),
                        "--request",
                        str(request_path),
                        "--out",
                        str(output),
                    ]
                )

            duplicate_request = root / "duplicate.json"
            duplicate_request.write_text(
                '{"review_version":"1.0.0","review_version":"1.0.0"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                review_files(card_path, duplicate_request)

    def test_documentation_keeps_review_separate_from_authorization(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_EVIDENCE.md").read_text(encoding="utf-8")
        for phrase in (
            "does not authorize training",
            "signal-derived",
            "independent categories",
            "redistribution_cleared = false",
            "no PLC",
            "no RUL",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
