from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_dataset import asset_split
from motorpulse.physical_evidence import create_review_manifest
from motorpulse.physical_training_readiness import (
    assess_training_readiness,
    main,
    validate_readiness_assessment,
)


def _sha(value: object) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _card(
    *,
    index: int,
    sample_rate_hz: int = 1024,
    sample_count: int = 1024,
    extracted_records: int = 9,
) -> dict:
    body = {
        "card_version": "1.0.0",
        "dataset_type": "user_supplied_local_physical_features",
        "session_id": f"session-{index}",
        "asset_id": f"PHYS-MTR-{index}",
        "device_id": f"esp32-lab-{index}",
        "feature_version": "1.0.0",
        "records": 10,
        "extracted_records": extracted_records,
        "abstained_records": 10 - extracted_records,
        "captured_start_utc": f"2026-10-{20 + index:02d}T10:00:00Z",
        "captured_end_utc": f"2026-10-{20 + index:02d}T10:00:09Z",
        "sampling_contracts": [
            {"sample_rate_hz": sample_rate_hz, "sample_count": sample_count}
        ],
        "sensor_provenance": {
            "device_family": "esp32",
            "firmware_version": "0.1.0",
            "accelerometer_model": "lab-accelerometer",
            "temperature_sensor_model": "lab-temperature",
            "rpm_sensor_model": "lab-tachometer",
        },
        "features_sha256": f"{index}" * 64,
        "canonical_frames_sha256": f"{index + 3}" * 64,
        "input_capture_sha256": f"{index + 6}" * 64,
        "calibration_status": "unverified",
        "label_status": "unknown",
        "failure_evidence_status": "unknown",
        "publication_status": "local_only_do_not_redistribute",
        "redistribution_cleared": False,
        "training_authorized": False,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "rul_authorized": False,
    }
    return {"card_id": "physical-run:" + _sha(body)[:24], **body}


def _evidence(
    *,
    evidence_id: str,
    digest_char: str,
    kind: str,
    origin: str,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_sha256": digest_char * 64,
        "evidence_date_utc": "2026-10-01T00:00:00Z",
        "expires_at_utc": None,
        "origin": origin,
        "kind": kind,
    }


def _request(index: int, *, calibration: bool = True, rights: bool = True, label: bool = False) -> dict:
    return {
        "review_version": "1.0.0",
        "reviewer_id": f"reviewer-{index}",
        "reviewed_at_utc": "2026-10-31T00:00:00Z",
        "calibration": {
            "review_status": "reviewed" if calibration else "not_reviewed",
            "evidence": [
                _evidence(
                    evidence_id=f"cal-{index}",
                    digest_char="a",
                    kind="calibration_certificate",
                    origin="external_record",
                )
            ]
            if calibration
            else [],
        },
        "label_failure": {
            "review_status": "reviewed" if label else "not_reviewed",
            "evidence": [
                _evidence(
                    evidence_id=f"label-{index}",
                    digest_char="b",
                    kind="inspection_record",
                    origin="external_record",
                )
            ]
            if label
            else [],
        },
        "rights_privacy": {
            "review_status": "reviewed" if rights else "not_reviewed",
            "evidence": [
                _evidence(
                    evidence_id=f"rights-{index}",
                    digest_char="c",
                    kind="ownership_record",
                    origin="owner_documentation",
                )
            ]
            if rights
            else [],
        },
    }


def _write_cards(root: Path, cards: list[dict]) -> list[Path]:
    paths: list[Path] = []
    for card in cards:
        path = root / f"{card['session_id']}.json"
        path.write_text(json.dumps(card), encoding="utf-8")
        paths.append(path)
    return paths


def _cohort(
    root: Path,
    *,
    label: bool = False,
    calibration: tuple[bool, bool, bool] = (True, True, True),
    rights: tuple[bool, bool, bool] = (True, True, True),
    third_sampling: tuple[int, int] = (1024, 1024),
    third_extracted: int = 9,
) -> tuple[dict, list[dict], list[dict]]:
    cards = [
        _card(index=1),
        _card(index=2),
        _card(
            index=3,
            sample_rate_hz=third_sampling[0],
            sample_count=third_sampling[1],
            extracted_records=third_extracted,
        ),
    ]
    plan = asset_split(_write_cards(root, cards), seed=42)
    reviews = [
        create_review_manifest(
            card,
            _request(
                index,
                calibration=calibration[index - 1],
                rights=rights[index - 1],
                label=label,
            ),
        )
        for index, card in enumerate(cards, start=1)
    ]
    return plan, cards, reviews


class PhysicalTrainingReadinessTests(unittest.TestCase):
    def test_unsupervised_cohort_can_be_ready_for_review_without_labels(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(Path(tmp))
            assessment = assess_training_readiness(plan, cards, reviews)
            self.assertEqual(assessment["training_readiness"], "ready_for_review")
            self.assertEqual(assessment["blockers"], [])
            self.assertFalse(assessment["evidence_policy"]["label_failure_review_required"])
            for field in (
                "redistribution_cleared",
                "training_authorized",
                "model_scoring_authorized",
                "diagnosis_authorized",
                "rul_authorized",
            ):
                self.assertFalse(assessment[field])
            validate_readiness_assessment(assessment)

    def test_supervised_failure_requires_independent_label_failure_review(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(Path(tmp))
            assessment = assess_training_readiness(
                plan,
                cards,
                reviews,
                target_mode="supervised_failure",
            )
            self.assertEqual(assessment["training_readiness"], "blocked")
            self.assertEqual(
                assessment["blockers"],
                [
                    "missing_label_failure_review:session-1",
                    "missing_label_failure_review:session-2",
                    "missing_label_failure_review:session-3",
                ],
            )

    def test_supervised_failure_can_only_reach_ready_for_review(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(Path(tmp), label=True)
            assessment = assess_training_readiness(
                plan,
                cards,
                reviews,
                target_mode="supervised_failure",
            )
            self.assertEqual(assessment["training_readiness"], "ready_for_review")
            self.assertFalse(assessment["training_authorized"])
            self.assertFalse(assessment["model_scoring_authorized"])

    def test_missing_calibration_and_rights_reviews_are_explicit_blockers(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(
                Path(tmp),
                calibration=(False, True, True),
                rights=(True, False, True),
            )
            assessment = assess_training_readiness(plan, cards, reviews)
            self.assertEqual(
                assessment["blockers"],
                [
                    "missing_calibration_review:session-1",
                    "missing_rights_privacy_review:session-2",
                ],
            )
            self.assertEqual(assessment["training_readiness"], "blocked")

    def test_sampling_mismatch_and_no_extracted_records_block_readiness(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(
                Path(tmp),
                third_sampling=(2048, 1024),
                third_extracted=0,
            )
            assessment = assess_training_readiness(plan, cards, reviews)
            self.assertEqual(
                assessment["blockers"],
                [
                    "incompatible_sampling_contract:session-3",
                    "no_extracted_records:session-3",
                ],
            )

    def test_split_hash_mutation_fails_closed(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(Path(tmp))
            forged = deepcopy(plan)
            forged["seed"] = 99
            with self.assertRaisesRegex(ValueError, "plan SHA-256"):
                assess_training_readiness(forged, cards, reviews)

    def test_asset_leakage_is_rejected_even_with_recomputed_plan_hash(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(Path(tmp))
            forged = deepcopy(plan)
            train_asset = forged["partitions"]["train"]["asset_ids"][0]
            forged["partitions"]["validation"]["asset_ids"].append(train_asset)
            body = {key: value for key, value in forged.items() if key != "plan_sha256"}
            forged["plan_sha256"] = _sha(body)
            with self.assertRaisesRegex(ValueError, "asset leaks across partitions"):
                assess_training_readiness(forged, cards, reviews)

    def test_review_mutation_and_duplicate_review_fail_closed(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(Path(tmp))
            mutated = deepcopy(reviews)
            mutated[0]["reviewer_id"] = "forged-reviewer"
            with self.assertRaisesRegex(ValueError, "review ID"):
                assess_training_readiness(plan, cards, mutated)

            duplicated = [reviews[0], reviews[1], reviews[1]]
            with self.assertRaisesRegex(ValueError, "duplicate physical evidence review"):
                assess_training_readiness(plan, cards, duplicated)

    def test_assessment_is_deterministic_across_input_order(self):
        with TemporaryDirectory() as tmp:
            plan, cards, reviews = _cohort(Path(tmp))
            first = assess_training_readiness(plan, cards, reviews)
            second = assess_training_readiness(
                plan,
                list(reversed(cards)),
                list(reversed(reviews)),
            )
            self.assertEqual(first, second)

    def test_cli_is_write_once_and_source_bound(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, cards, reviews = _cohort(root)
            split_path = root / "split.json"
            split_path.write_text(json.dumps(plan), encoding="utf-8")
            card_paths: list[Path] = []
            review_paths: list[Path] = []
            for index, (card, review) in enumerate(zip(cards, reviews), start=1):
                card_path = root / f"input-card-{index}.json"
                review_path = root / f"review-{index}.json"
                card_path.write_text(json.dumps(card), encoding="utf-8")
                review_path.write_text(json.dumps(review), encoding="utf-8")
                card_paths.append(card_path)
                review_paths.append(review_path)
            output = root / "readiness.json"
            args = ["--split", str(split_path)]
            for card_path in card_paths:
                args.extend(["--card", str(card_path)])
            for review_path in review_paths:
                args.extend(["--review", str(review_path)])
            args.extend(["--out", str(output)])
            self.assertEqual(main(args), 0)
            assessment = json.loads(output.read_text(encoding="utf-8"))
            validate_readiness_assessment(assessment)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(args)

    def test_documentation_preserves_readiness_only_boundary(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_TRAINING_READINESS.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "ready_for_review is not training authorization",
            "training_authorized = false",
            "asset-disjoint",
            "signal-derived truth is not allowed",
            "no PLC",
            "MP-016 remains ON HOLD",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
