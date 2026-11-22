from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse import physical_final_test_scorer as scorer
from motorpulse.physical_dataset import _read_features
from motorpulse.physical_final_test_approval_record import (
    create_final_test_approval_record,
)
from motorpulse.physical_training_approval_request import _sha
from test_physical_final_test_approval_record import _fixture


def _approved(root):
    request, decision, chain, sources = _fixture(root)
    record = create_final_test_approval_record(request, decision, *chain)
    return record, request, decision, chain, sources


class PhysicalFinalTestScorerTests(unittest.TestCase):
    def test_frozen_model_scores_only_test_partition(self):
        with TemporaryDirectory() as tmp:
            record, request, decision, chain, _ = _approved(Path(tmp))
            model, bundle, split = chain[4], chain[9], chain[11]
            test_ids = set(split["partitions"]["test"]["card_ids"])
            original = _sha(model)
            result = scorer.score_physical_final_test(record, request, decision, *chain)
            self.assertEqual(result["partition"], "test")
            self.assertEqual({row["card_id"] for row in result["rows"]}, test_ids)
            self.assertEqual(result["model_sha256"], original)
            self.assertEqual(_sha(model), original)
            self.assertEqual(result["threshold"], model["calibration"]["threshold"])
            self.assertEqual(result["validation_result_sha256"], _sha(chain[0]))
            self.assertEqual(result["final_test_approval_record_sha256"], _sha(record))
            self.assertEqual(result["train_rows_consumed"], 0)
            self.assertEqual(result["validation_rows_consumed"], 0)
            self.assertTrue(result["test_scoring_completed"])
            for row in result["rows"]:
                if row["status"] == "abstained":
                    self.assertIsNone(row["score"])
                    self.assertIsNone(row["review_flag"])
                else:
                    self.assertEqual(
                        row["review_flag"], row["score"] > result["threshold"]
                    )
            self.assertEqual(
                result["counts"]["test_rows_scored"],
                sum(
                    entry["extracted_records"] for entry in bundle["partitions"]["test"]
                ),
            )
            self.assertEqual(
                result["counts"]["test_rows_abstained"],
                sum(
                    entry["abstained_records"] for entry in bundle["partitions"]["test"]
                ),
            )
            for key in (
                "score_is_failure_probability",
                "model_refit_performed",
                "preprocessing_refit_performed",
                "threshold_recalibration_performed",
                "diagnosis_performed",
                "failure_probability_estimated",
                "rul_estimated",
                "redistribution_cleared",
                "deployment_authorized",
            ):
                self.assertIs(result[key], False)
            self.assertNotIn(tmp, json.dumps(result))
            scorer.validate_physical_final_test_result(
                result, record, request, decision, *chain
            )

    def test_no_test_calculation_before_approval(self):
        with TemporaryDirectory() as tmp:
            record, request, decision, chain, _ = _approved(Path(tmp))
            with patch.object(scorer, "_score", wraps=scorer._score) as score:
                with self.assertRaises(ValueError):
                    scorer.score_physical_final_test(
                        {**record, "test_scoring_authorized": False},
                        request,
                        decision,
                        *chain,
                    )
                with self.assertRaises(ValueError):
                    scorer.score_physical_final_test(
                        record,
                        request,
                        {**decision, "human_affirmation": "continue"},
                        *chain,
                    )
                score.assert_not_called()

    def test_tampered_result_rejected(self):
        with TemporaryDirectory() as tmp:
            record, request, decision, chain, _ = _approved(Path(tmp))
            result = scorer.score_physical_final_test(record, request, decision, *chain)
            for key, value in (
                ("test_scoring_completed", 1),
                ("threshold", result["threshold"] + 1),
                ("deployment_authorized", True),
            ):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    scorer.validate_physical_final_test_result(
                        {**result, key: value}, record, request, decision, *chain
                    )
            forged = deepcopy(result)
            row = next(row for row in forged["rows"] if row["status"] == "scored")
            row["score"] += 1
            with self.assertRaises(ValueError):
                scorer.validate_physical_final_test_result(
                    forged, record, request, decision, *chain
                )

    def test_snapshots_are_shared_across_validation_and_scoring(self):
        with TemporaryDirectory() as tmp:
            record, request, decision, chain, sources = _approved(Path(tmp))
            expected = scorer.score_physical_final_test(
                record, request, decision, *chain
            )
            original = sources[4][0]
            real_validate = scorer.validate_final_test_approval_record

            def mutate_original(*args):
                real_validate(*args)
                original.write_bytes(original.read_bytes() + b" ")

            with patch.object(
                scorer,
                "validate_final_test_approval_record",
                side_effect=mutate_original,
            ):
                actual = scorer.score_physical_final_test(
                    record, request, decision, *chain
                )
            self.assertEqual(actual, expected)
            with self.assertRaises(ValueError):
                scorer.score_physical_final_test(record, request, decision, *chain)

    def test_deterministic_order_and_test_vector_isolation(self):
        with TemporaryDirectory() as tmp:
            record, request, decision, chain, sources = _approved(Path(tmp))
            model, split = chain[4], chain[11]
            cards = {card["features_sha256"]: card["card_id"] for card in chain[12]}
            test_ids = set(split["partitions"]["test"]["card_ids"])
            expected_hashes = set()
            expected_scores = {}
            for path in sources[4]:
                rows, digest = _read_features(path)
                if cards[digest] in test_ids:
                    for row in rows:
                        if row["feature_status"] == "extracted":
                            key = row["input_frame_sha256"]
                            expected_hashes.add(key)
                            expected_scores[key] = scorer._score(
                                scorer._vector(row),
                                model["preprocessing"]["center"],
                                model["preprocessing"]["effective_scales"],
                            )
            with patch.object(scorer, "_vector", wraps=scorer._vector) as vector:
                first = scorer.score_physical_final_test(
                    record, request, decision, *chain
                )
            self.assertEqual(
                {call.args[0]["input_frame_sha256"] for call in vector.call_args_list},
                expected_hashes,
            )
            self.assertEqual(
                {
                    row["input_frame_sha256"]: row["score"]
                    for row in first["rows"]
                    if row["status"] == "scored"
                },
                expected_scores,
            )
            changed = list(chain)
            for index in (12, 13, 14):
                changed[index] = list(reversed(changed[index]))
            self.assertEqual(
                first,
                scorer.score_physical_final_test(record, request, decision, *changed),
            )

    def test_snapshot_limits_and_cleanup(self):
        with TemporaryDirectory() as tmp:
            record, request, decision, chain, _ = _approved(Path(tmp))
            with patch.object(scorer, "MAX_SNAPSHOT_BYTES", 1):
                with self.assertRaisesRegex(ValueError, "snapshot exceeds"):
                    scorer.score_physical_final_test(record, request, decision, *chain)
            captured = []
            with scorer._snapshot_features(chain[14]) as snapshots:
                captured.extend(snapshots)
                self.assertTrue(all(path.is_file() for path in captured))
            self.assertTrue(all(not path.exists() for path in captured))

    def test_cli_write_once(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            record, request, decision, chain, sources = _approved(root)
            names = (
                "final-test-approval-record",
                "final-test-request",
                "final-test-decision",
                "validation-result",
                "evaluation-approval-record",
                "evaluation-request",
                "evaluation-decision",
                "model",
                "training-approval-record",
                "training-request",
                "training-decision",
                "preregistration",
                "bundle",
                "readiness",
                "split",
            )
            args = []
            for name, value in zip(names, (record, request, decision, *chain[:12])):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                args.extend((f"--{name}", str(path)))
            protocol = root / "protocol.json"
            protocol.write_text(json.dumps(chain[15]), encoding="utf-8")
            for name, entries in (
                ("card", sources[5]),
                ("review", sources[6]),
                ("feature", sources[4]),
            ):
                for path in entries:
                    args.extend((f"--{name}", str(path)))
            output = root / "final-test-result.json"
            args.extend(("--protocol", str(protocol), "--out", str(output)))
            self.assertEqual(scorer.main(args), 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["partition"], "test")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                scorer.main(args)


if __name__ == "__main__":
    unittest.main()
