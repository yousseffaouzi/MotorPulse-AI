from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_final_test_approval_record import (
    approval_files,
    create_final_test_approval_record,
    main,
    validate_final_test_approval_record,
    write_final_test_approval_record,
)
from motorpulse.physical_training_approval_request import _sha
from test_physical_final_test_approval_request import _final_request_sources, _request


def _fixture(root):
    sources = _final_request_sources(root)
    request = _request(sources)
    decision = {
        "final_test_approval_decision_version": "1.0.0",
        "final_test_request_id": request["request_id"],
        "final_test_request_sha256": _sha(request),
        "approval_challenge_sha256": request["approval_challenge_sha256"],
        "decision": "approve_final_test_scoring_only",
        "human_affirmation": request["approval_phrase"],
        "reviewer_assertion": "fixture-only-not-real-approval",
        "decided_at_utc": "2026-11-22T20:00:00Z",
    }
    # Exact MP-070 API order; source fixture remains entirely synthetic.
    chain = tuple(
        sources[i] for i in (17, 16, 14, 15, 13, 12, 10, 11, 9, 7, 3, 0, 1, 2, 4, 8)
    )
    return request, decision, chain, sources


class PhysicalFinalTestApprovalRecordTests(unittest.TestCase):
    def test_exact_decision_authorizes_only_final_test(self):
        with TemporaryDirectory() as tmp:
            request, decision, chain, _ = _fixture(Path(tmp))
            record = create_final_test_approval_record(request, decision, *chain)
            validate_final_test_approval_record(record, request, decision, *chain)
            self.assertEqual(record["final_test_request_sha256"], _sha(request))
            self.assertEqual(
                record["validation_result_sha256"], request["validation_result_sha256"]
            )
            self.assertEqual(record["model_sha256"], request["model_sha256"])
            self.assertEqual(record["decision_sha256"], _sha(decision))
            self.assertTrue(record["test_scoring_authorized"])
            self.assertFalse(record["test_scoring_completed"])
            self.assertEqual(record["test_rows_consumed"], 0)
            self.assertEqual(
                record["reviewer_identity_assurance"], "self_asserted_not_authenticated"
            )
            self.assertEqual(record["decision_signature_assurance"], "none")
            for key in (
                "train_scoring_authorized",
                "validation_rescoring_authorized",
                "model_refit_authorized",
                "preprocessing_refit_authorized",
                "threshold_recalibration_authorized",
                "diagnosis_authorized",
                "failure_probability_authorized",
                "rul_authorized",
                "deployment_authorized",
                "redistribution_cleared",
            ):
                self.assertIs(record[key], False)
            self.assertNotIn(request["approval_phrase"], json.dumps(record))
            self.assertNotIn(tmp, json.dumps(record))

    def test_wrong_decision_is_rejected(self):
        with TemporaryDirectory() as tmp:
            request, decision, chain, _ = _fixture(Path(tmp))
            for key, value in (
                ("human_affirmation", "continue"),
                ("final_test_request_id", "other"),
                ("final_test_request_sha256", "0" * 64),
                ("approval_challenge_sha256", "0" * 64),
                ("decision", "approve_deployment"),
                ("reviewer_assertion", " "),
                ("decided_at_utc", "2026-02-30T00:00:00Z"),
            ):
                forged = {**decision, key: value}
                with self.subTest(key=key), self.assertRaises(ValueError):
                    create_final_test_approval_record(request, forged, *chain)

    def test_request_type_substitution_is_rejected(self):
        with TemporaryDirectory() as tmp:
            request, decision, chain, _ = _fixture(Path(tmp))
            for key, value in (
                ("training_completed", 1),
                ("test_rows_consumed", False),
            ):
                forged = {**request, key: value}
                bound = {**decision, "final_test_request_sha256": _sha(forged)}
                with self.subTest(key=key), self.assertRaises(ValueError):
                    create_final_test_approval_record(forged, bound, *chain)

    def test_record_edits_cannot_expand_scope(self):
        with TemporaryDirectory() as tmp:
            request, decision, chain, _ = _fixture(Path(tmp))
            record = create_final_test_approval_record(request, decision, *chain)
            for key, value in (
                ("deployment_authorized", True),
                ("validation_rescoring_authorized", True),
                ("test_scoring_authorized", 1),
                ("test_rows_consumed", False),
                ("test_scoring_completed", True),
                ("decision_signature_assurance", "signed"),
            ):
                forged = {**record, key: value}
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate_final_test_approval_record(
                        forged, request, decision, *chain
                    )

    def test_changed_validation_and_feature_bytes_rejected(self):
        with TemporaryDirectory() as tmp:
            request, decision, chain, sources = _fixture(Path(tmp))
            record = create_final_test_approval_record(request, decision, *chain)
            changed = list(chain)
            changed[0] = deepcopy(chain[0])
            changed[0]["result_id"] = "forged"
            with self.assertRaises(ValueError):
                validate_final_test_approval_record(record, request, decision, *changed)
            feature = sources[4][0]
            feature.write_bytes(feature.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                validate_final_test_approval_record(record, request, decision, *chain)

    def test_source_order_is_deterministic(self):
        with TemporaryDirectory() as tmp:
            request, decision, chain, _ = _fixture(Path(tmp))
            first = create_final_test_approval_record(request, decision, *chain)
            changed = list(chain)
            for index in (12, 13, 14):
                changed[index] = list(reversed(changed[index]))
            second = create_final_test_approval_record(request, decision, *changed)
            self.assertEqual(first, second)

    def test_cli_requires_decision_and_is_write_once(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            request, decision, chain, sources = _fixture(root)
            names = (
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
            paths = []
            args = []
            for name, value in zip(names, (request, decision, *chain[:12])):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
                args.extend((f"--{name}", str(path)))
            protocol = root / "protocol.json"
            protocol.write_text(json.dumps(chain[15]), encoding="utf-8")
            output = root / "final-test-approval.json"
            for name, entries in (
                ("card", sources[5]),
                ("review", sources[6]),
                ("feature", sources[4]),
            ):
                for path in entries:
                    args.extend((f"--{name}", str(path)))
            args.extend(("--protocol", str(protocol), "--out", str(output)))
            record = approval_files(
                *paths, sources[5], sources[6], sources[4], protocol
            )
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), record)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                write_final_test_approval_record(output, record)
            paths[1].write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                approval_files(*paths, sources[5], sources[6], sources[4], protocol)


if __name__ == "__main__":
    unittest.main()
