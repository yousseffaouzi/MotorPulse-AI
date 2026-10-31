from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_training_approval_record import (
    create_approval_record,
    main,
    validate_approval_record,
)
from motorpulse.physical_training_approval_request import create_approval_request, _sha
from test_physical_training_approval_request import _sources


def _approved_sources(root: Path):
    (
        split,
        cards,
        reviews,
        readiness,
        features,
        card_paths,
        review_paths,
        bundle,
        protocol,
        preregistration,
    ) = _sources(root)
    request = create_approval_request(
        preregistration,
        bundle,
        readiness,
        split,
        cards,
        reviews,
        features,
        protocol,
    )
    decision = {
        "approval_decision_version": "1.0.0",
        "request_id": request["request_id"],
        "request_sha256": _sha(request),
        "approval_challenge_sha256": request["approval_challenge_sha256"],
        "decision": "approve_offline_training_only",
        "human_affirmation": request["approval_phrase"],
        "reviewer_assertion": "test-fixture-reviewer-not-real-approval",
        "decided_at_utc": "2026-10-31T21:00:00Z",
    }
    return (
        split,
        cards,
        reviews,
        readiness,
        features,
        card_paths,
        review_paths,
        bundle,
        protocol,
        preregistration,
        request,
        decision,
    )


class PhysicalTrainingApprovalRecordTests(unittest.TestCase):
    def test_exact_separate_decision_yields_narrow_training_record(self):
        with TemporaryDirectory() as tmp:
            (
                split,
                cards,
                reviews,
                readiness,
                features,
                _,
                _,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(Path(tmp))
            record = create_approval_record(
                request,
                decision,
                preregistration,
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            self.assertTrue(
                record["approval_record_id"].startswith("physical-training-approval:")
            )
            self.assertEqual(
                record["approval_state"], "approved_for_offline_training_only"
            )
            self.assertEqual(record["approved_capability"], "offline_training_only")
            self.assertEqual(
                record["approved_operations"], request["requested_operations"]
            )
            self.assertTrue(record["training_authorized"])
            for field in (
                "redistribution_cleared",
                "model_scoring_authorized",
                "diagnosis_authorized",
                "rul_authorized",
                "deployment_authorized",
            ):
                self.assertFalse(record[field])
            self.assertEqual(
                record["reviewer_identity_assurance"],
                "self_asserted_not_authenticated",
            )
            self.assertEqual(record["decision_signature_assurance"], "none")
            rendered = json.dumps(record, sort_keys=True)
            self.assertNotIn("APPROVE OFFLINE TRAINING REQUEST", rendered)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_generic_continue_or_wrong_phrase_never_approves(self):
        with TemporaryDirectory() as tmp:
            (
                split,
                cards,
                reviews,
                readiness,
                features,
                _,
                _,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(Path(tmp))
            for phrase in ("continue", "great work, continue", "APPROVE"):
                forged = deepcopy(decision)
                forged["human_affirmation"] = phrase
                with self.subTest(phrase=phrase), self.assertRaisesRegex(
                    ValueError, "exact MP-064 approval phrase"
                ):
                    create_approval_record(
                        request,
                        forged,
                        preregistration,
                        bundle,
                        readiness,
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )

    def test_decision_must_bind_exact_request_hash_id_and_challenge(self):
        with TemporaryDirectory() as tmp:
            (
                split,
                cards,
                reviews,
                readiness,
                features,
                _,
                _,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(Path(tmp))
            changes = (
                ("request_id", "physical-training-request:wrong", "request ID"),
                ("request_sha256", "0" * 64, "request SHA-256"),
                ("approval_challenge_sha256", "0" * 64, "challenge"),
            )
            for field, value, message in changes:
                forged = deepcopy(decision)
                forged[field] = value
                with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, message
                ):
                    create_approval_record(
                        request,
                        forged,
                        preregistration,
                        bundle,
                        readiness,
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )

    def test_reviewer_and_timestamp_are_explicit_but_not_authenticated(self):
        with TemporaryDirectory() as tmp:
            (
                split,
                cards,
                reviews,
                readiness,
                features,
                _,
                _,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(Path(tmp))
            for reviewer in ("", " reviewer", "reviewer\n"):
                forged = deepcopy(decision)
                forged["reviewer_assertion"] = reviewer
                with self.subTest(reviewer=reviewer), self.assertRaisesRegex(
                    ValueError, "reviewer_assertion"
                ):
                    create_approval_record(
                        request,
                        forged,
                        preregistration,
                        bundle,
                        readiness,
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )
            for timestamp in (
                "2026-10-31T22:00:00+01:00",
                "2026-10-31 21:00:00Z",
                "2026-02-30T21:00:00Z",
            ):
                forged = deepcopy(decision)
                forged["decided_at_utc"] = timestamp
                with self.subTest(timestamp=timestamp), self.assertRaisesRegex(
                    ValueError, "decided_at_utc"
                ):
                    create_approval_record(
                        request,
                        forged,
                        preregistration,
                        bundle,
                        readiness,
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )

    def test_record_cannot_broaden_operations_or_downstream_authorization(self):
        with TemporaryDirectory() as tmp:
            (
                split,
                cards,
                reviews,
                readiness,
                features,
                _,
                _,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(Path(tmp))
            record = create_approval_record(
                request,
                decision,
                preregistration,
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            forged = deepcopy(record)
            forged["approved_operations"].append("score_test")
            with self.assertRaisesRegex(ValueError, "does not match exact request"):
                validate_approval_record(
                    forged,
                    request,
                    decision,
                    preregistration,
                    bundle,
                    readiness,
                    split,
                    cards,
                    reviews,
                    features,
                    protocol,
                )
            for field in (
                "model_scoring_authorized",
                "diagnosis_authorized",
                "rul_authorized",
                "deployment_authorized",
                "redistribution_cleared",
            ):
                forged = deepcopy(record)
                forged[field] = True
                with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, f"keep {field}=false"
                ):
                    validate_approval_record(
                        forged,
                        request,
                        decision,
                        preregistration,
                        bundle,
                        readiness,
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )

    def test_feature_byte_change_invalidates_existing_approval_record(self):
        with TemporaryDirectory() as tmp:
            (
                split,
                cards,
                reviews,
                readiness,
                features,
                _,
                _,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(Path(tmp))
            record = create_approval_record(
                request,
                decision,
                preregistration,
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            path = features[0]
            path.write_text(
                path.read_text(encoding="utf-8").rstrip("\n") + "  \n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                validate_approval_record(
                    record,
                    request,
                    decision,
                    preregistration,
                    bundle,
                    readiness,
                    split,
                    cards,
                    reviews,
                    features,
                    protocol,
                )

    def test_source_input_order_does_not_change_approval_record(self):
        with TemporaryDirectory() as tmp:
            (
                split,
                cards,
                reviews,
                readiness,
                features,
                _,
                _,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(Path(tmp))
            first = create_approval_record(
                request,
                decision,
                preregistration,
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            second = create_approval_record(
                request,
                dict(reversed(list(decision.items()))),
                preregistration,
                bundle,
                readiness,
                split,
                list(reversed(cards)),
                list(reversed(reviews)),
                list(reversed(features)),
                protocol,
            )
            self.assertEqual(first, second)

    def test_cli_write_once_and_documented_human_boundary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (
                split,
                _,
                _,
                readiness,
                features,
                card_paths,
                review_paths,
                bundle,
                protocol,
                preregistration,
                request,
                decision,
            ) = _approved_sources(root)
            paths = {
                "request": root / "approval-request.json",
                "decision": root / "human-decision.json",
                "preregistration": root / "preregistration.json",
                "bundle": root / "bundle.json",
                "readiness": root / "readiness.json",
                "split": root / "split.json",
                "protocol": root / "protocol.json",
            }
            payloads = {
                "request": request,
                "decision": decision,
                "preregistration": preregistration,
                "bundle": bundle,
                "readiness": readiness,
                "split": split,
                "protocol": protocol,
            }
            for name, path in paths.items():
                path.write_text(json.dumps(payloads[name]), encoding="utf-8")
            output = root / "approval-record.json"
            args = [
                "--request",
                str(paths["request"]),
                "--decision",
                str(paths["decision"]),
                "--preregistration",
                str(paths["preregistration"]),
                "--bundle",
                str(paths["bundle"]),
                "--readiness",
                str(paths["readiness"]),
                "--split",
                str(paths["split"]),
            ]
            for path in card_paths:
                args.extend(["--card", str(path)])
            for path in review_paths:
                args.extend(["--review", str(path)])
            for path in features:
                args.extend(["--feature", str(path)])
            args.extend(
                ["--protocol", str(paths["protocol"]), "--out", str(output)]
            )
            self.assertEqual(main(args), 0)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(saved["training_authorized"])
            self.assertFalse(saved["model_scoring_authorized"])
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_TRAINING_APPROVAL_RECORD.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "separately authored human decision",
            "generic instruction such as `continue` is not approval",
            "self-asserted and is not authenticated",
            "training_authorized = true",
            "model_scoring_authorized = false",
            "does not train a model",
            "not a standalone bearer token",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
