from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_final_test_approval_request import (
    REQUESTED_OPERATIONS,
    create_final_test_approval_request,
    main,
    validate_final_test_approval_request,
)
from motorpulse.physical_training_approval_request import _sha
from test_physical_validation_scorer import _score, _scoring_sources


def _final_request_sources(root: Path):
    sources = _scoring_sources(root)
    validation_result = _score(sources)
    return (*sources, validation_result)


def _request(sources):
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
        evaluation_approval_record,
        validation_result,
    ) = sources
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
        split,
        cards,
        reviews,
        features,
        protocol,
    )


class PhysicalFinalTestApprovalRequestTests(unittest.TestCase):
    def test_exact_validation_result_yields_pending_test_only_request(self):
        with TemporaryDirectory() as tmp:
            sources = _final_request_sources(Path(tmp))
            request = _request(sources)
            model = sources[13]
            evaluation_approval_record = sources[16]
            validation_result = sources[17]
            self.assertTrue(
                request["request_id"].startswith("physical-final-test-request:")
            )
            self.assertEqual(
                request["validation_result_id"], validation_result["result_id"]
            )
            self.assertEqual(
                request["validation_result_sha256"], _sha(validation_result)
            )
            self.assertEqual(request["model_id"], model["model_id"])
            self.assertEqual(request["model_sha256"], _sha(model))
            self.assertEqual(
                request["evaluation_approval_record_id"],
                evaluation_approval_record["evaluation_approval_record_id"],
            )
            self.assertEqual(
                request["requested_capability"], "offline_final_test_scoring_only"
            )
            self.assertEqual(request["requested_operations"], REQUESTED_OPERATIONS)
            self.assertEqual(
                request["partition_roles"],
                {
                    "train": "frozen_no_refit_no_rescore",
                    "validation": "completed_frozen_no_rescore",
                    "test": (
                        "score_with_frozen_model_after_separate_explicit_approval"
                    ),
                },
            )
            self.assertEqual(
                request["approval_state"], "pending_explicit_human_approval"
            )
            self.assertTrue(request["training_completed"])
            self.assertTrue(request["validation_scoring_completed"])
            self.assertEqual(request["test_rows_consumed"], 0)
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
                self.assertFalse(request[field])
            rendered = json.dumps(request, sort_keys=True)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_tampered_validation_result_is_rejected(self):
        with TemporaryDirectory() as tmp:
            sources = list(_final_request_sources(Path(tmp)))
            forged = deepcopy(sources[17])
            scored = next(
                row for row in forged["rows"] if row["status"] == "scored"
            )
            scored["review_flag"] = not scored["review_flag"]
            sources[17] = forged
            with self.assertRaisesRegex(
                ValueError, "does not match exact approved model and sources"
            ):
                _request(tuple(sources))

    def test_pending_request_cannot_be_promoted_by_editing_json(self):
        with TemporaryDirectory() as tmp:
            sources = _final_request_sources(Path(tmp))
            request = _request(sources)
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
                evaluation_approval_record,
                validation_result,
            ) = sources
            for field in (
                "test_scoring_authorized",
                "validation_rescoring_authorized",
                "model_refit_authorized",
                "threshold_recalibration_authorized",
                "diagnosis_authorized",
                "deployment_authorized",
            ):
                forged = deepcopy(request)
                forged[field] = True
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, f"keep {field}=false"),
                ):
                    validate_final_test_approval_request(
                        forged,
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
                        split,
                        cards,
                        reviews,
                        features,
                        protocol,
                    )
            approved = deepcopy(request)
            approved["approval_state"] = "approved"
            with self.assertRaisesRegex(ValueError, "must remain pending"):
                validate_final_test_approval_request(
                    approved,
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
                    split,
                    cards,
                    reviews,
                    features,
                    protocol,
                )

    def test_feature_byte_change_invalidates_before_request(self):
        with TemporaryDirectory() as tmp:
            sources = _final_request_sources(Path(tmp))
            features = sources[4]
            features[0].write_text(
                features[0].read_text(encoding="utf-8").rstrip("\n") + "  \n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                _request(sources)

    def test_source_input_order_does_not_change_request(self):
        with TemporaryDirectory() as tmp:
            sources = _final_request_sources(Path(tmp))
            first = _request(sources)
            mutable = list(sources)
            mutable[1] = list(reversed(mutable[1]))
            mutable[2] = list(reversed(mutable[2]))
            mutable[4] = list(reversed(mutable[4]))
            second = _request(tuple(mutable))
            self.assertEqual(first, second)

    def test_cli_write_once_and_documented_boundary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = _final_request_sources(root)
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
                evaluation_approval_record,
                validation_result,
            ) = sources
            payloads = {
                "validation-result": validation_result,
                "evaluation-approval-record": evaluation_approval_record,
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
            output = root / "final-test-request.json"
            args = [
                "--validation-result",
                str(paths["validation-result"]),
                "--evaluation-approval-record",
                str(paths["evaluation-approval-record"]),
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
            self.assertFalse(saved["test_scoring_authorized"])
            self.assertFalse(saved["test_scoring_completed"])
            self.assertEqual(saved["test_rows_consumed"], 0)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        project_root = Path(__file__).resolve().parents[1]
        text = (project_root / "docs/PHYSICAL_FINAL_TEST_APPROVAL.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "pending request only",
            "does not read or score test rows",
            "exact MP-069 validation result",
            "Validation success is not test approval",
            "generic `continue` is not approval",
            "test_scoring_authorized = false",
            "no refit or recalibration",
            "local_only_do_not_redistribute",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
