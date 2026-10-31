from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from statistics import fmean
from tempfile import TemporaryDirectory
import unittest

from motorpulse.feature_pipeline import FEATURES
from motorpulse.physical_dataset import _read_features
from motorpulse.physical_offline_trainer import (
    main,
    train_physical_model,
    validate_physical_model,
)
from motorpulse.physical_training_approval_record import create_approval_record
from test_physical_training_approval_record import _approved_sources


def _training_sources(root: Path):
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
        request,
        decision,
    ) = _approved_sources(root)
    approval_record = create_approval_record(
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
        approval_record,
    )


class PhysicalOfflineTrainerTests(unittest.TestCase):
    def test_exact_approved_chain_fits_narrow_train_only_model(self):
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
                approval_record,
            ) = _training_sources(Path(tmp))
            model = train_physical_model(
                approval_record,
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
            self.assertTrue(model["model_id"].startswith("physical-model:"))
            self.assertEqual(
                model["model_family"], "standardized_distance_baseline_v1"
            )
            self.assertTrue(model["training_authorized"])
            self.assertTrue(model["training_completed"])
            self.assertEqual(model["training"]["partition"], "train")
            self.assertEqual(model["training"]["heldout_rows_consumed"], 0)
            self.assertEqual(
                model["heldout_partitions"],
                {
                    "validation": "untouched_no_fit_no_score",
                    "test": "untouched_no_fit_no_score",
                },
            )
            expected_train_ids = sorted(split["partitions"]["train"]["card_ids"])
            self.assertEqual(model["training"]["train_card_ids"], expected_train_ids)
            for field in (
                "redistribution_cleared",
                "model_scoring_authorized",
                "diagnosis_authorized",
                "failure_probability_authorized",
                "rul_authorized",
                "deployment_authorized",
            ):
                self.assertFalse(model[field])
            self.assertFalse(model["score_is_failure_probability"])
            self.assertIsNone(model["remaining_useful_life"])
            rendered = json.dumps(model, sort_keys=True)
            self.assertNotIn("APPROVE OFFLINE TRAINING REQUEST", rendered)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_fitted_center_comes_only_from_train_extracted_rows(self):
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
                approval_record,
            ) = _training_sources(Path(tmp))
            model = train_physical_model(
                approval_record,
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
            train_digests = {
                entry["features_sha256"] for entry in bundle["partitions"]["train"]
            }
            train_rows = []
            heldout_extracted = 0
            for path in features:
                rows, digest = _read_features(path)
                extracted = [
                    row for row in rows if row["feature_status"] == "extracted"
                ]
                if digest in train_digests:
                    train_rows.extend(extracted)
                else:
                    heldout_extracted += len(extracted)
            self.assertGreater(heldout_extracted, 0)
            expected = [
                fmean(float(row[name]) for row in train_rows) for name in FEATURES
            ]
            self.assertEqual(model["preprocessing"]["center"], expected)
            self.assertEqual(
                model["training"]["extracted_rows_consumed"], len(train_rows)
            )
            self.assertEqual(model["training"]["heldout_rows_consumed"], 0)

    def test_broadened_or_stale_approval_fails_closed(self):
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
                approval_record,
            ) = _training_sources(Path(tmp))
            for field in (
                "model_scoring_authorized",
                "diagnosis_authorized",
                "deployment_authorized",
            ):
                forged = deepcopy(approval_record)
                forged[field] = True
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, f"keep {field}=false"),
                ):
                    train_physical_model(
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

    def test_feature_byte_change_invalidates_training_before_fit(self):
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
                approval_record,
            ) = _training_sources(Path(tmp))
            features[0].write_text(
                features[0].read_text(encoding="utf-8").rstrip("\n") + "  \n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                train_physical_model(
                    approval_record,
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

    def test_model_artifact_cannot_enable_downstream_claims(self):
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
                approval_record,
            ) = _training_sources(Path(tmp))
            model = train_physical_model(
                approval_record,
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
                "failure_probability_authorized",
                "rul_authorized",
                "deployment_authorized",
                "redistribution_cleared",
            ):
                forged = deepcopy(model)
                forged[field] = True
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, f"keep {field}=false"),
                ):
                    validate_physical_model(
                        forged,
                        approval_record,
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

    def test_source_input_order_does_not_change_model(self):
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
                approval_record,
            ) = _training_sources(Path(tmp))
            first = train_physical_model(
                approval_record,
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
            second = train_physical_model(
                approval_record,
                request,
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
                request,
                decision,
                approval_record,
            ) = _training_sources(root)
            del cards, reviews
            payloads = {
                "approval-record": approval_record,
                "request": request,
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
            output = root / "physical-model.json"
            args = [
                "--approval-record",
                str(paths["approval-record"]),
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
                [
                    "--protocol",
                    str(paths["protocol"]),
                    "--out",
                    str(output),
                ]
            )
            self.assertEqual(main(args), 0)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(saved["training_completed"])
            self.assertFalse(saved["model_scoring_authorized"])
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_OFFLINE_TRAINING.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "complete MP-065 approval chain",
            "train partition only",
            "validation and test are untouched",
            "does not score any physical row",
            "not a failure probability",
            "local_only_do_not_redistribute",
            "fixture decisions are non-operational",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
