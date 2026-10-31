from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_experiment_bundle import create_experiment_bundle
from motorpulse.physical_experiment_preregistration import (
    MODEL_FAMILY,
    create_preregistration,
    main,
    validate_preregistration,
)
from test_physical_experiment_bundle import _cohort


def _protocol(**overrides: object) -> dict:
    protocol = {
        "protocol_version": "1.0.0",
        "model_family": MODEL_FAMILY,
        "threshold_quantile": 0.99,
        "seed": 17,
        "minimum_extracted_records": {
            "train": 1,
            "validation": 1,
            "test": 1,
        },
    }
    protocol.update(overrides)
    return protocol


def _prepared(root: Path):
    split, cards, reviews, readiness, features, card_paths, review_paths = _cohort(root)
    bundle = create_experiment_bundle(readiness, split, cards, reviews, features)
    return (
        split,
        cards,
        reviews,
        readiness,
        features,
        card_paths,
        review_paths,
        bundle,
    )


class PhysicalExperimentPreregistrationTests(unittest.TestCase):
    def test_ready_bundle_becomes_eligible_without_authorizing_training(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _, bundle = _prepared(
                Path(tmp)
            )
            preregistration = create_preregistration(
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                _protocol(),
            )
            self.assertTrue(
                preregistration["preregistration_id"].startswith(
                    "physical-preregistration:"
                )
            )
            self.assertEqual(
                preregistration["authorization_state"],
                "eligible_for_explicit_training_approval",
            )
            self.assertEqual(preregistration["blockers"], [])
            for field in (
                "redistribution_cleared",
                "training_authorized",
                "model_scoring_authorized",
                "diagnosis_authorized",
                "rul_authorized",
            ):
                self.assertFalse(preregistration[field])
            rendered = json.dumps(preregistration, sort_keys=True)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_design_freezes_train_only_fit_threshold_and_untouched_test(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _, bundle = _prepared(
                Path(tmp)
            )
            preregistration = create_preregistration(
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                _protocol(),
            )
            design = preregistration["experiment_design"]
            self.assertEqual(design["fit_partition"], "train")
            self.assertEqual(design["preprocessing_fit_partition"], "train")
            self.assertEqual(design["threshold_partition"], "train")
            self.assertEqual(design["validation_role"], "review_only_no_fit")
            self.assertEqual(design["test_role"], "final_only_no_fit")
            self.assertEqual(
                design["input_features"],
                ["rms_g", "crest_factor", "band_80_400_rms_g", "temperature_c", "rpm"],
            )

    def test_minimum_record_shortfall_blocks_instead_of_authorizing(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _, bundle = _prepared(
                Path(tmp)
            )
            protocol = _protocol(
                minimum_extracted_records={
                    "train": 2,
                    "validation": 1,
                    "test": 1,
                }
            )
            preregistration = create_preregistration(
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            self.assertEqual(preregistration["authorization_state"], "blocked")
            self.assertEqual(
                preregistration["blockers"],
                ["insufficient_train_extracted_records:1<2"],
            )
            self.assertFalse(preregistration["training_authorized"])

    def test_protocol_rejects_model_quantile_seed_and_minimum_drift(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _, bundle = _prepared(
                Path(tmp)
            )
            cases = (
                (_protocol(model_family="opaque_neural_model"), "model family"),
                (_protocol(threshold_quantile=1.0), "threshold_quantile"),
                (_protocol(seed=True), "seed"),
                (
                    _protocol(
                        minimum_extracted_records={
                            "train": 0,
                            "validation": 1,
                            "test": 1,
                        }
                    ),
                    "train minimum",
                ),
            )
            for protocol, message in cases:
                with self.subTest(message=message):
                    with self.assertRaisesRegex(ValueError, message):
                        create_preregistration(
                            bundle,
                            readiness,
                            split,
                            cards,
                            reviews,
                            features,
                            protocol,
                        )

    def test_source_order_does_not_change_preregistration(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _, bundle = _prepared(
                Path(tmp)
            )
            first = create_preregistration(
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                _protocol(),
            )
            second = create_preregistration(
                bundle,
                readiness,
                split,
                list(reversed(cards)),
                list(reversed(reviews)),
                list(reversed(features)),
                _protocol(),
            )
            self.assertEqual(first, second)

    def test_feature_byte_mutation_invalidates_existing_preregistration(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _, bundle = _prepared(
                Path(tmp)
            )
            protocol = _protocol()
            preregistration = create_preregistration(
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            path = features[0]
            original = path.read_text(encoding="utf-8")
            path.write_text(
                original.rstrip("\n") + "  \n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                validate_preregistration(
                    preregistration,
                    bundle,
                    readiness,
                    split,
                    cards,
                    reviews,
                    features,
                    protocol,
                )

    def test_authorization_fields_cannot_be_promoted_by_editing_json(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _, bundle = _prepared(
                Path(tmp)
            )
            protocol = _protocol()
            preregistration = create_preregistration(
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                protocol,
            )
            forged = deepcopy(preregistration)
            forged["training_authorized"] = True
            with self.assertRaisesRegex(ValueError, "keep training_authorized=false"):
                validate_preregistration(
                    forged,
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
                cards,
                reviews,
                readiness,
                features,
                card_paths,
                review_paths,
                bundle,
            ) = _prepared(root)
            bundle_path = root / "bundle.json"
            readiness_path = root / "readiness.json"
            split_path = root / "split.json"
            protocol_path = root / "protocol.json"
            output = root / "preregistration.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            split_path.write_text(json.dumps(split), encoding="utf-8")
            protocol_path.write_text(json.dumps(_protocol()), encoding="utf-8")
            args = [
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
            validate_preregistration(
                saved,
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
                _protocol(),
            )
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_EXPERIMENT_PREREGISTRATION.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "eligible_for_explicit_training_approval",
            "train-only",
            "test_role = final_only_no_fit",
            "training_authorized = false",
            "does not train a model",
            "no PLC",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
