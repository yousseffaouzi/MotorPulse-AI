from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_evaluation_approval_request import (
    REQUESTED_OPERATIONS,
    create_evaluation_approval_request,
    main,
    validate_evaluation_approval_request,
)
from motorpulse.physical_offline_trainer import train_physical_model
from motorpulse.physical_training_approval_request import _sha
from test_physical_offline_trainer import _training_sources


def _evaluation_sources(root: Path):
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
        decision,
        approval_record,
    ) = _training_sources(root)
    model = train_physical_model(
        approval_record,
        training_request,
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
        decision,
        approval_record,
        model,
    )


class PhysicalEvaluationApprovalRequestTests(unittest.TestCase):
    def test_exact_model_chain_yields_pending_validation_only_request(self):
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
                decision,
                approval_record,
                model,
            ) = _evaluation_sources(Path(tmp))
            request = create_evaluation_approval_request(
                model,
                approval_record,
                training_request,
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
                request["request_id"].startswith("physical-evaluation-request:")
            )
            self.assertEqual(request["model_id"], model["model_id"])
            self.assertEqual(request["model_sha256"], _sha(model))
            self.assertEqual(
                request["training_approval_record_id"],
                approval_record["approval_record_id"],
            )
            self.assertEqual(
                request["requested_capability"], "offline_validation_scoring_only"
            )
            self.assertEqual(request["requested_operations"], REQUESTED_OPERATIONS)
            self.assertEqual(
                request["partition_roles"],
                {
                    "train": "frozen_no_refit_no_rescore",
                    "validation": (
                        "score_with_frozen_model_after_separate_explicit_approval"
                    ),
                    "test": "untouched_no_score",
                },
            )
            self.assertEqual(
                request["approval_state"], "pending_explicit_human_approval"
            )
            self.assertTrue(request["training_completed"])
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
                self.assertFalse(request[field])
            rendered = json.dumps(request, sort_keys=True)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_tampered_model_is_rejected_before_request(self):
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
                decision,
                approval_record,
                model,
            ) = _evaluation_sources(Path(tmp))
            forged = deepcopy(model)
            forged["calibration"]["threshold"] += 1.0
            with self.assertRaisesRegex(
                ValueError, "does not match exact approved sources"
            ):
                create_evaluation_approval_request(
                    forged,
                    approval_record,
                    training_request,
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

    def test_pending_request_cannot_be_promoted_by_editing_json(self):
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
                decision,
                approval_record,
                model,
            ) = _evaluation_sources(Path(tmp))
            request = create_evaluation_approval_request(
                model,
                approval_record,
                training_request,
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
                "validation_scoring_authorized",
                "test_scoring_authorized",
                "model_refit_authorized",
                "diagnosis_authorized",
                "deployment_authorized",
            ):
                forged = deepcopy(request)
                forged[field] = True
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, f"keep {field}=false"),
                ):
                    validate_evaluation_approval_request(
                        forged,
                        model,
                        approval_record,
                        training_request,
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
            approved = deepcopy(request)
            approved["approval_state"] = "approved"
            with self.assertRaisesRegex(ValueError, "must remain pending"):
                validate_evaluation_approval_request(
                    approved,
                    model,
                    approval_record,
                    training_request,
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

    def test_feature_byte_change_invalidates_existing_model_chain(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                decision,
                approval_record,
                model,
            ) = _evaluation_sources(root)
            features[0].write_text(
                features[0].read_text(encoding="utf-8").rstrip("\n") + "  \n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                create_evaluation_approval_request(
                    model,
                    approval_record,
                    training_request,
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

    def test_source_order_does_not_change_request(self):
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
                decision,
                approval_record,
                model,
            ) = _evaluation_sources(Path(tmp))
            first = create_evaluation_approval_request(
                model,
                approval_record,
                training_request,
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
            second = create_evaluation_approval_request(
                model,
                approval_record,
                training_request,
                decision,
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

    def test_cli_write_once_and_documented_boundary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                decision,
                approval_record,
                model,
            ) = _evaluation_sources(root)
            del cards, reviews
            payloads = {
                "model": model,
                "approval-record": approval_record,
                "training-request": training_request,
                "decision": decision,
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
            output = root / "evaluation-request.json"
            args = [
                "--model",
                str(paths["model"]),
                "--approval-record",
                str(paths["approval-record"]),
                "--training-request",
                str(paths["training-request"]),
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
                [
                    "--protocol",
                    str(paths["protocol"]),
                    "--out",
                    str(output),
                ]
            )
            self.assertEqual(main(args), 0)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["approval_state"], "pending_explicit_human_approval")
            self.assertFalse(saved["validation_scoring_authorized"])
            self.assertFalse(saved["test_scoring_authorized"])
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_MODEL_EVALUATION_APPROVAL.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "pending request only",
            "does not score any physical row",
            "validation partition only",
            "test partition remains untouched",
            "no refit or recalibration",
            "not a failure probability",
            "generic `continue` is not approval",
            "local_only_do_not_redistribute",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
