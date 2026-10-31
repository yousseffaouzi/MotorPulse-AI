from __future__ import annotations

from copy import deepcopy
import json
from math import pi, sin
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_dataset import asset_split, create_run_card, write_json
from motorpulse.physical_evidence import create_review_manifest
from motorpulse.physical_experiment_bundle import (
    create_experiment_bundle,
    main,
    validate_experiment_bundle,
)
from motorpulse.physical_features import extract_capture, write_feature_outputs
from motorpulse.physical_training_readiness import assess_training_readiness
from motorpulse.sensor_gateway import CANONICAL_UNITS


def _frame(*, index: int) -> dict:
    sample_rate_hz = 1024
    sample_count = 1024
    rpm = 1800.0
    shaft_hz = rpm / 60.0
    samples = [
        0.5 * sin(2 * pi * shaft_hz * sample_index / sample_rate_hz)
        for sample_index in range(sample_count)
    ]
    return {
        "capture_version": "1.0.0",
        "source": "physical_sensor",
        "device_id": f"esp32-lab-{index}",
        "asset_id": f"PHYS-MTR-{index}",
        "sequence": 1,
        "device_uptime_ms": 1000,
        "captured_at_utc": f"2026-10-{20 + index:02d}T10:00:00Z",
        "sample_rate_hz": sample_rate_hz,
        "sample_count": sample_count,
        "units": dict(CANONICAL_UNITS),
        "quality": {"vibration": "good", "temperature": "good", "rpm": "good"},
        "acceleration_g": samples,
        "temperature_c": 30.0 + index,
        "rpm": rpm,
        "provenance": {
            "device_family": "esp32",
            "firmware_version": "0.1.0",
            "accelerometer_model": "lab-accelerometer",
            "temperature_sensor_model": "lab-temperature",
            "rpm_sensor_model": "lab-tachometer",
        },
    }


def _evidence(*, evidence_id: str, digest_char: str, kind: str, origin: str) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_sha256": digest_char * 64,
        "evidence_date_utc": "2026-10-01T00:00:00Z",
        "expires_at_utc": None,
        "origin": origin,
        "kind": kind,
    }


def _review_request(index: int) -> dict:
    return {
        "review_version": "1.0.0",
        "reviewer_id": f"reviewer-{index}",
        "reviewed_at_utc": "2026-10-31T00:00:00Z",
        "calibration": {
            "review_status": "reviewed",
            "evidence": [
                _evidence(
                    evidence_id=f"cal-{index}",
                    digest_char="a",
                    kind="calibration_certificate",
                    origin="external_record",
                )
            ],
        },
        "label_failure": {"review_status": "not_reviewed", "evidence": []},
        "rights_privacy": {
            "review_status": "reviewed",
            "evidence": [
                _evidence(
                    evidence_id=f"rights-{index}",
                    digest_char="b",
                    kind="ownership_record",
                    origin="owner_documentation",
                )
            ],
        },
    }


def _cohort(root: Path) -> tuple[dict, list[dict], list[dict], dict, list[Path], list[Path], list[Path]]:
    cards: list[dict] = []
    reviews: list[dict] = []
    feature_paths: list[Path] = []
    card_paths: list[Path] = []
    review_paths: list[Path] = []
    for index in range(1, 4):
        session = root / f"session-{index}"
        session.mkdir()
        capture = session / "capture.jsonl"
        capture.write_text(
            json.dumps(
                _frame(index=index),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        rows, report = extract_capture(capture)
        features = session / "features.jsonl"
        feature_report = session / "feature-report.json"
        write_feature_outputs(rows, report, features, feature_report)
        card = create_run_card(
            features,
            feature_report,
            session_id=f"session-{index}",
        )
        card_path = session / "run-card.json"
        write_json(card_path, card)
        review = create_review_manifest(card, _review_request(index))
        review_path = session / "review.json"
        write_json(review_path, review)
        cards.append(card)
        reviews.append(review)
        feature_paths.append(features)
        card_paths.append(card_path)
        review_paths.append(review_path)
    split = asset_split(card_paths, seed=42)
    readiness = assess_training_readiness(split, cards, reviews)
    return split, cards, reviews, readiness, feature_paths, card_paths, review_paths


class PhysicalExperimentBundleTests(unittest.TestCase):
    def test_ready_cohort_binds_exact_feature_files_without_authorization(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _ = _cohort(Path(tmp))
            bundle = create_experiment_bundle(
                readiness,
                split,
                cards,
                reviews,
                features,
            )
            self.assertTrue(bundle["bundle_id"].startswith("physical-bundle:"))
            self.assertEqual(len(bundle["source_files"]), 3)
            self.assertEqual(
                sum(len(bundle["partitions"][name]) for name in ("train", "validation", "test")),
                3,
            )
            for field in (
                "redistribution_cleared",
                "training_authorized",
                "model_scoring_authorized",
                "diagnosis_authorized",
                "rul_authorized",
            ):
                self.assertFalse(bundle[field])
            rendered = json.dumps(bundle, sort_keys=True)
            self.assertNotIn("acceleration_g", rendered)
            self.assertNotIn(str(Path(tmp)), rendered)

    def test_feature_path_order_does_not_change_bundle(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _ = _cohort(Path(tmp))
            first = create_experiment_bundle(readiness, split, cards, reviews, features)
            second = create_experiment_bundle(
                readiness,
                split,
                list(reversed(cards)),
                list(reversed(reviews)),
                list(reversed(features)),
            )
            self.assertEqual(first, second)

    def test_byte_level_change_after_audit_invalidates_bundle(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _ = _cohort(Path(tmp))
            bundle = create_experiment_bundle(readiness, split, cards, reviews, features)
            path = features[0]
            original = path.read_text(encoding="utf-8")
            path.write_text(original.rstrip("\n") + "  \n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(ValueError, "bundle does not match sources"):
                validate_experiment_bundle(
                    bundle,
                    readiness,
                    split,
                    cards,
                    reviews,
                    features,
                )

    def test_semantic_feature_tampering_fails_card_binding(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _ = _cohort(Path(tmp))
            row = json.loads(features[0].read_text(encoding="utf-8"))
            row["temperature_c"] += 1.0
            features[0].write_text(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(ValueError, "not part of the ready cohort"):
                create_experiment_bundle(readiness, split, cards, reviews, features)

    def test_missing_or_duplicate_feature_file_fails_closed(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _ = _cohort(Path(tmp))
            with self.assertRaisesRegex(ValueError, "exactly one physical feature file"):
                create_experiment_bundle(
                    readiness,
                    split,
                    cards,
                    reviews,
                    features[:2],
                )
            duplicated = [features[0], features[1], features[1]]
            with self.assertRaisesRegex(ValueError, "duplicate physical feature file"):
                create_experiment_bundle(
                    readiness,
                    split,
                    cards,
                    reviews,
                    duplicated,
                )

    def test_mutated_readiness_cannot_authorize_bundle(self):
        with TemporaryDirectory() as tmp:
            split, cards, reviews, readiness, features, _, _ = _cohort(Path(tmp))
            forged = deepcopy(readiness)
            forged["training_authorized"] = True
            with self.assertRaisesRegex(ValueError, "keep training_authorized=false"):
                create_experiment_bundle(forged, split, cards, reviews, features)

    def test_cli_is_write_once_and_metadata_only(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            split, cards, reviews, readiness, features, card_paths, review_paths = _cohort(root)
            split_path = root / "split.json"
            readiness_path = root / "readiness.json"
            split_path.write_text(json.dumps(split), encoding="utf-8")
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            output = root / "bundle.json"
            args = ["--readiness", str(readiness_path), "--split", str(split_path)]
            for path in card_paths:
                args.extend(["--card", str(path)])
            for path in review_paths:
                args.extend(["--review", str(path)])
            for path in features:
                args.extend(["--feature", str(path)])
            args.extend(["--out", str(output)])
            self.assertEqual(main(args), 0)
            bundle = json.loads(output.read_text(encoding="utf-8"))
            validate_experiment_bundle(
                bundle,
                readiness,
                split,
                cards,
                reviews,
                features,
            )
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

    def test_documentation_keeps_bundle_audit_only(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_EXPERIMENT_BUNDLE.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "exact feature bytes",
            "metadata-only",
            "training_authorized = false",
            "does not fit a model",
            "no PLC",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
