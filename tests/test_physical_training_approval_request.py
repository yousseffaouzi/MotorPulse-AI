from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_experiment_preregistration import create_preregistration
from motorpulse.physical_training_approval_request import (
    create_approval_request,
    main,
    validate_approval_request,
)
from test_physical_experiment_preregistration import _prepared, _protocol


def _sources(root: Path, protocol: dict | None = None):
    (
        split,
        cards,
        reviews,
        readiness,
        features,
        card_paths,
        review_paths,
        bundle,
    ) = _prepared(root)
    protocol = _protocol() if protocol is None else protocol
    preregistration = create_preregistration(
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
    )


class PhysicalTrainingApprovalRequestTests(unittest.TestCase):
    def test_eligible_preregistration_yields_pending_request_only(self):
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
            ) = _sources(Path(tmp))
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
            self.assertTrue(
                request["request_id"].startswith("physical-training-request:")
            )
            self.assertEqual(
                request["approval_state"], "pending_explicit_human_approval"
            )
            self.assertEqual(request["requested_capability"], "offline_training_only")
            self.assertEqual(
                request["requested_operations"],
                [
                    "fit_preprocessing_on_train",
                    "fit_model_on_train",
                    "derive_threshold_on_train",
                ],
            )
            for field in (
                "redistribution_cleared",
                "training_authorized",
                "model_scoring_authorized",
                "diagnosis_authorized",
                "rul_authorized",
            ):
                self.assertFalse(request[field])
            rendered = json.dumps(request, sort_keys=True)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_challenge_phrase_binds_exact_request_and_preregistration(self):
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
            ) = _sources(Path(tmp))
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
            phrase = request["approval_phrase"]
            self.assertEqual(
                phrase,
                "APPROVE OFFLINE TRAINING REQUEST "
                + request["request_id"]
                + " CHALLENGE "
                + request["approval_challenge_sha256"],
            )
            self.assertEqual(
                request["preregistration_id"], preregistration["preregistration_id"]
            )
            self.assertEqual(
                len(request["approval_challenge_sha256"]),
                64,
            )

    def test_partition_scope_is_frozen_and_cannot_be_broadened(self):
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
            ) = _sources(Path(tmp))
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
            self.assertEqual(
                request["partition_roles"],
                {
                    "fit_partition": "train",
                    "preprocessing_fit_partition": "train",
                    "threshold_partition": "train",
                    "validation_role": "review_only_no_fit",
                    "test_role": "final_only_no_fit",
                },
            )
            forged = deepcopy(request)
            forged["requested_operations"].append("score_test")
            with self.assertRaisesRegex(ValueError, "does not match exact sources"):
                validate_approval_request(
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

    def test_blocked_preregistration_cannot_produce_request(self):
        with TemporaryDirectory() as tmp:
            blocked_protocol = _protocol(
                minimum_extracted_records={
                    "train": 2,
                    "validation": 1,
                    "test": 1,
                }
            )
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
            ) = _sources(Path(tmp), blocked_protocol)
            self.assertEqual(preregistration["authorization_state"], "blocked")
            with self.assertRaisesRegex(
                ValueError, "requires an MP-063 preregistration"
            ):
                create_approval_request(
                    preregistration,
                    bundle,
                    readiness,
                    split,
                    cards,
                    reviews,
                    features,
                    protocol,
                )

    def test_input_order_does_not_change_request(self):
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
            ) = _sources(Path(tmp))
            first = create_approval_request(
                preregistration,
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            second = create_approval_request(
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

    def test_feature_byte_mutation_invalidates_request(self):
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
            ) = _sources(Path(tmp))
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
            path = features[0]
            path.write_text(
                path.read_text(encoding="utf-8").rstrip("\n") + "  \n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                validate_approval_request(
                    request,
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
            ) = _sources(Path(tmp))
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
            forged = deepcopy(request)
            forged["training_authorized"] = True
            with self.assertRaisesRegex(ValueError, "keep training_authorized=false"):
                validate_approval_request(
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
            forged = deepcopy(request)
            forged["approval_state"] = "approved"
            with self.assertRaisesRegex(ValueError, "pending explicit human approval"):
                validate_approval_request(
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

    def test_cli_write_once_and_documented_boundary(self):
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
            ) = _sources(root)
            preregistration_path = root / "preregistration.json"
            bundle_path = root / "bundle.json"
            readiness_path = root / "readiness.json"
            split_path = root / "split.json"
            protocol_path = root / "protocol.json"
            output = root / "approval-request.json"
            preregistration_path.write_text(
                json.dumps(preregistration), encoding="utf-8"
            )
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            split_path.write_text(json.dumps(split), encoding="utf-8")
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
            args = [
                "--preregistration",
                str(preregistration_path),
                "--bundle",
                str(bundle_path),
                "--readiness",
                str(readiness_path),
                "--split",
                str(split_path),
            ]
            for path in card_paths:
                args.extend(["--card", str(path)])
            for path in review_paths:
                args.extend(["--review", str(path)])
            for path in features:
                args.extend(["--feature", str(path)])
            args.extend(["--protocol", str(protocol_path), "--out", str(output)])
            self.assertEqual(main(args), 0)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["approval_state"], "pending_explicit_human_approval")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_TRAINING_APPROVAL_REQUEST.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "pending_explicit_human_approval",
            "offline_training_only",
            "not an approval",
            "training_authorized = false",
            "does not train a model",
            "no PLC",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
