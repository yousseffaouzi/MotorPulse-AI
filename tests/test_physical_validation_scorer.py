from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_dataset import _read_features
from motorpulse.physical_evaluation_approval_record import (
    create_evaluation_approval_record,
)
from motorpulse.physical_validation_scorer import (
    main,
    score_physical_validation,
    validate_physical_validation_result,
)
from test_physical_evaluation_approval_record import _approved_evaluation_sources


def _scoring_sources(root: Path):
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
        evaluation_request,
        evaluation_decision,
    ) = _approved_evaluation_sources(root)
    evaluation_approval_record = create_evaluation_approval_record(
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
        evaluation_approval_record,
    )


def _score(sources):
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
    ) = sources
    return score_physical_validation(
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


class PhysicalValidationScorerTests(unittest.TestCase):
    def test_exact_mp068_chain_scores_validation_only(self):
        with TemporaryDirectory() as tmp:
            sources = _scoring_sources(Path(tmp))
            result = _score(sources)
            split, _, _, _, _, _, _, bundle, _, _, _, _, _, model, _, _, record = (
                sources
            )
            validation_ids = set(split["partitions"]["validation"]["card_ids"])
            train_ids = set(split["partitions"]["train"]["card_ids"])
            test_ids = set(split["partitions"]["test"]["card_ids"])
            self.assertTrue(result["result_id"].startswith("physical-validation-result:"))
            self.assertEqual(result["result_kind"], "review_only_anomaly_scores")
            self.assertEqual(result["partition"], "validation")
            self.assertEqual(result["model_id"], model["model_id"])
            self.assertEqual(
                result["evaluation_approval_record_id"],
                record["evaluation_approval_record_id"],
            )
            self.assertEqual(
                {row["card_id"] for row in result["rows"]}, validation_ids
            )
            self.assertFalse(
                {row["card_id"] for row in result["rows"]} & (train_ids | test_ids)
            )
            expected_scored = sum(
                entry["extracted_records"]
                for entry in bundle["partitions"]["validation"]
            )
            expected_abstained = sum(
                entry["abstained_records"]
                for entry in bundle["partitions"]["validation"]
            )
            self.assertEqual(
                result["counts"]["validation_rows_scored"], expected_scored
            )
            self.assertEqual(
                result["counts"]["validation_rows_abstained"], expected_abstained
            )
            self.assertEqual(result["train_rows_consumed"], 0)
            self.assertEqual(result["test_rows_consumed"], 0)
            self.assertTrue(result["validation_scoring_authorized"])
            self.assertTrue(result["validation_scoring_completed"])
            self.assertFalse(result["test_scoring_authorized"])
            self.assertFalse(result["score_is_failure_probability"])
            rendered = json.dumps(result, sort_keys=True)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn("temperature_c", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_scores_use_frozen_threshold_with_strict_comparison(self):
        with TemporaryDirectory() as tmp:
            sources = _scoring_sources(Path(tmp))
            result = _score(sources)
            model = sources[13]
            self.assertEqual(result["threshold"], model["calibration"]["threshold"])
            self.assertEqual(result["threshold_comparison"], "score > threshold")
            for row in result["rows"]:
                if row["status"] == "abstained":
                    self.assertIsNone(row["score"])
                    self.assertIsNone(row["review_flag"])
                else:
                    self.assertEqual(
                        row["review_flag"], row["score"] > result["threshold"]
                    )
            self.assertFalse(result["threshold_recalibration_performed"])
            self.assertFalse(result["model_refit_performed"])
            self.assertFalse(result["preprocessing_refit_performed"])

    def test_only_validation_feature_rows_appear(self):
        with TemporaryDirectory() as tmp:
            sources = _scoring_sources(Path(tmp))
            result = _score(sources)
            split, cards, _, _, features = sources[:5]
            validation_ids = set(split["partitions"]["validation"]["card_ids"])
            cards_by_digest = {card["features_sha256"]: card for card in cards}
            expected = set()
            non_validation = set()
            for path in features:
                rows, digest = _read_features(path)
                card_id = cards_by_digest[digest]["card_id"]
                identities = {
                    (card_id, row["sequence"], row["input_frame_sha256"])
                    for row in rows
                }
                if card_id in validation_ids:
                    expected |= identities
                else:
                    non_validation |= identities
            actual = {
                (row["card_id"], row["sequence"], row["input_frame_sha256"])
                for row in result["rows"]
            }
            self.assertEqual(actual, expected)
            self.assertFalse(actual & non_validation)

    def test_broadened_or_stale_mp068_record_fails_closed(self):
        with TemporaryDirectory() as tmp:
            sources = _scoring_sources(Path(tmp))
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
                record,
            ) = sources
            for field in (
                "test_scoring_authorized",
                "model_refit_authorized",
                "threshold_recalibration_authorized",
                "diagnosis_authorized",
                "deployment_authorized",
            ):
                forged = deepcopy(record)
                forged[field] = True
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, f"keep {field}=false"),
                ):
                    score_physical_validation(
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

    def test_feature_byte_change_invalidates_before_result(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = _scoring_sources(root)
            features = sources[4]
            features[0].write_text(
                features[0].read_text(encoding="utf-8").rstrip("\n") + "  \n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                _score(sources)

    def test_result_cannot_be_promoted_to_downstream_claims(self):
        with TemporaryDirectory() as tmp:
            sources = _scoring_sources(Path(tmp))
            result = _score(sources)
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
                record,
            ) = sources
            for field in (
                "test_scoring_authorized",
                "deployment_authorized",
                "redistribution_cleared",
                "model_refit_performed",
                "preprocessing_refit_performed",
                "threshold_recalibration_performed",
                "diagnosis_performed",
                "failure_probability_estimated",
                "rul_estimated",
            ):
                forged = deepcopy(result)
                forged[field] = True
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, f"keep {field}=false"),
                ):
                    validate_physical_validation_result(
                        forged,
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

    def test_source_input_order_does_not_change_result(self):
        with TemporaryDirectory() as tmp:
            sources = _scoring_sources(Path(tmp))
            first = _score(sources)
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
                record,
            ) = sources
            second = score_physical_validation(
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
                list(reversed(cards)),
                list(reversed(reviews)),
                list(reversed(features)),
                protocol,
            )
            self.assertEqual(first, second)

    def test_cli_write_once_and_documented_boundary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = _scoring_sources(root)
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
                record,
            ) = sources
            payloads = {
                "evaluation-approval-record": record,
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
            output = root / "validation-result.json"
            args = [
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
            self.assertEqual(saved["partition"], "validation")
            self.assertEqual(saved["test_rows_consumed"], 0)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_VALIDATION_SCORING.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "full MP-068 approval chain",
            "validation partition only",
            "strict `score > threshold`",
            "review flag is not a diagnosis",
            "test partition remains untouched",
            "no refit or recalibration",
            "local_only_do_not_redistribute",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
