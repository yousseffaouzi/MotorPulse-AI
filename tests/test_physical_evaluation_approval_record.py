from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_evaluation_approval_record import (
    create_evaluation_approval_record,
    main,
    validate_evaluation_approval_record,
)
from motorpulse.physical_evaluation_approval_request import (
    create_evaluation_approval_request,
)
from motorpulse.physical_training_approval_request import _sha
from test_physical_evaluation_approval_request import _evaluation_sources


def _approved_evaluation_sources(root: Path):
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
        training_request,
        training_decision,
        training_approval_record,
        model,
    ) = _evaluation_sources(root)
    evaluation_request = create_evaluation_approval_request(
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split,
        cards,
        reviews,
        features,
        protocol,
    )
    evaluation_decision = {
        "evaluation_approval_decision_version": "1.0.0",
        "evaluation_request_id": evaluation_request["request_id"],
        "evaluation_request_sha256": _sha(evaluation_request),
        "approval_challenge_sha256": evaluation_request[
            "approval_challenge_sha256"
        ],
        "decision": "approve_validation_scoring_only",
        "human_affirmation": evaluation_request["approval_phrase"],
        "reviewer_assertion": "test-fixture-reviewer-not-real-approval",
        "decided_at_utc": "2026-11-01T00:40:00Z",
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
        training_request,
        training_decision,
        training_approval_record,
        model,
        evaluation_request,
        evaluation_decision,
    )


class PhysicalEvaluationApprovalRecordTests(unittest.TestCase):
    def test_exact_separate_decision_yields_validation_only_record(self):
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = _approved_evaluation_sources(Path(tmp))
            record = create_evaluation_approval_record(
                evaluation_request,
                evaluation_decision,
                model,
                training_approval_record,
                training_request,
                training_decision,
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
                record["evaluation_approval_record_id"].startswith(
                    "physical-evaluation-approval:"
                )
            )
            self.assertEqual(
                record["approval_state"], "approved_for_validation_scoring_only"
            )
            self.assertEqual(
                record["approved_capability"], "offline_validation_scoring_only"
            )
            self.assertEqual(
                record["approved_operations"], evaluation_request["requested_operations"]
            )
            self.assertTrue(record["training_completed"])
            self.assertTrue(record["validation_scoring_authorized"])
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
                self.assertFalse(record[field])
            self.assertEqual(
                record["reviewer_identity_assurance"],
                "self_asserted_not_authenticated",
            )
            self.assertEqual(record["decision_signature_assurance"], "none")
            rendered = json.dumps(record, sort_keys=True)
            self.assertNotIn("APPROVE PHYSICAL VALIDATION SCORING REQUEST", rendered)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_generic_continue_or_wrong_phrase_never_approves(self):
        with TemporaryDirectory() as tmp:
            sources = _approved_evaluation_sources(Path(tmp))
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = sources
            for phrase in ("continue", "great great continue", "APPROVE"):
                forged = deepcopy(evaluation_decision)
                forged["human_affirmation"] = phrase
                with (
                    self.subTest(phrase=phrase),
                    self.assertRaisesRegex(ValueError, "exact MP-067 approval phrase"),
                ):
                    create_evaluation_approval_record(
                        evaluation_request,
                        forged,
                        model,
                        training_approval_record,
                        training_request,
                        training_decision,
                        preregistration,
                        bundle,
                        readiness,
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )

    def test_decision_binds_exact_request_hash_id_and_challenge(self):
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = _approved_evaluation_sources(Path(tmp))
            changes = (
                (
                    "evaluation_request_id",
                    "physical-evaluation-request:wrong",
                    "request ID",
                ),
                ("evaluation_request_sha256", "0" * 64, "request SHA-256"),
                ("approval_challenge_sha256", "0" * 64, "challenge"),
            )
            for field, value, message in changes:
                forged = deepcopy(evaluation_decision)
                forged[field] = value
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, message),
                ):
                    create_evaluation_approval_record(
                        evaluation_request,
                        forged,
                        model,
                        training_approval_record,
                        training_request,
                        training_decision,
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = _approved_evaluation_sources(Path(tmp))
            for reviewer in ("", " reviewer", "reviewer\n"):
                forged = deepcopy(evaluation_decision)
                forged["reviewer_assertion"] = reviewer
                with (
                    self.subTest(reviewer=reviewer),
                    self.assertRaisesRegex(ValueError, "reviewer_assertion"),
                ):
                    create_evaluation_approval_record(
                        evaluation_request,
                        forged,
                        model,
                        training_approval_record,
                        training_request,
                        training_decision,
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
                "2026-11-01T01:40:00+01:00",
                "2026-11-01 00:40:00Z",
                "2026-02-30T00:40:00Z",
            ):
                forged = deepcopy(evaluation_decision)
                forged["decided_at_utc"] = timestamp
                with (
                    self.subTest(timestamp=timestamp),
                    self.assertRaisesRegex(ValueError, "decided_at_utc"),
                ):
                    create_evaluation_approval_record(
                        evaluation_request,
                        forged,
                        model,
                        training_approval_record,
                        training_request,
                        training_decision,
                        preregistration,
                        bundle,
                        readiness,
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )

    def test_record_cannot_broaden_scoring_or_downstream_authorization(self):
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = _approved_evaluation_sources(Path(tmp))
            record = create_evaluation_approval_record(
                evaluation_request,
                evaluation_decision,
                model,
                training_approval_record,
                training_request,
                training_decision,
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
            forged["approved_operations"].append("score_test_partition")
            with self.assertRaisesRegex(ValueError, "does not match exact request"):
                validate_evaluation_approval_record(
                    forged,
                    evaluation_request,
                    evaluation_decision,
                    model,
                    training_approval_record,
                    training_request,
                    training_decision,
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
                "train_scoring_authorized",
                "test_scoring_authorized",
                "model_refit_authorized",
                "preprocessing_refit_authorized",
                "threshold_recalibration_authorized",
                "diagnosis_authorized",
                "failure_probability_authorized",
                "rul_authorized",
                "deployment_authorized",
                "redistribution_cleared",
            ):
                forged = deepcopy(record)
                forged[field] = True
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, f"keep {field}=false"),
                ):
                    validate_evaluation_approval_record(
                        forged,
                        evaluation_request,
                        evaluation_decision,
                        model,
                        training_approval_record,
                        training_request,
                        training_decision,
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = _approved_evaluation_sources(Path(tmp))
            record = create_evaluation_approval_record(
                evaluation_request,
                evaluation_decision,
                model,
                training_approval_record,
                training_request,
                training_decision,
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
                validate_evaluation_approval_record(
                    record,
                    evaluation_request,
                    evaluation_decision,
                    model,
                    training_approval_record,
                    training_request,
                    training_decision,
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = _approved_evaluation_sources(Path(tmp))
            first = create_evaluation_approval_record(
                evaluation_request,
                evaluation_decision,
                model,
                training_approval_record,
                training_request,
                training_decision,
                preregistration,
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            second = create_evaluation_approval_record(
                evaluation_request,
                dict(reversed(list(evaluation_decision.items()))),
                model,
                training_approval_record,
                training_request,
                training_decision,
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
                training_request,
                training_decision,
                training_approval_record,
                model,
                evaluation_request,
                evaluation_decision,
            ) = _approved_evaluation_sources(root)
            payloads = {
                "evaluation-request": evaluation_request,
                "evaluation-decision": evaluation_decision,
                "model": model,
                "training-approval-record": training_approval_record,
                "training-request": training_request,
                "training-decision": training_decision,
                "preregistration": preregistration,
                "bundle": bundle,
                "readiness": readiness,
                "split": split,
                "protocol": protocol,
            }
            paths = {}
            for name, payload in payloads.items():
                path = root / f"{name}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths[name] = path
            output = root / "evaluation-approval-record.json"
            args = [
                "--evaluation-request",
                str(paths["evaluation-request"]),
                "--evaluation-decision",
                str(paths["evaluation-decision"]),
                "--model",
                str(paths["model"]),
                "--training-approval-record",
                str(paths["training-approval-record"]),
                "--training-request",
                str(paths["training-request"]),
                "--training-decision",
                str(paths["training-decision"]),
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
                [
                    "--protocol",
                    str(paths["protocol"]),
                    "--out",
                    str(output),
                ]
            )
            self.assertEqual(main(args), 0)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(saved["validation_scoring_authorized"])
            self.assertFalse(saved["test_scoring_authorized"])
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_EVALUATION_APPROVAL_RECORD.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "separately authored human decision",
            "generic instruction such as `continue` is not approval",
            "self-asserted and is not authenticated",
            "validation_scoring_authorized = true",
            "test_scoring_authorized = false",
            "does not score any physical row",
            "not a standalone bearer token",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
