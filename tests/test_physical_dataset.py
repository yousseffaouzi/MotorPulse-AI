from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from math import pi, sin
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_dataset import (
    asset_split,
    create_run_card,
    main,
    validate_run_card,
    write_json,
)
from motorpulse.physical_features import extract_capture, write_feature_outputs
from motorpulse.sensor_gateway import CANONICAL_UNITS


def _frame(
    *,
    asset_id: str,
    device_id: str,
    timestamp: str,
    temperature_c: float,
    rpm: float = 1800.0,
) -> dict:
    sample_rate_hz = 1024
    sample_count = 1024
    shaft_hz = rpm / 60
    samples = [
        0.5 * sin(2 * pi * shaft_hz * index / sample_rate_hz)
        for index in range(sample_count)
    ]
    return {
        "capture_version": "1.0.0",
        "source": "physical_sensor",
        "device_id": device_id,
        "asset_id": asset_id,
        "sequence": 1,
        "device_uptime_ms": 1000,
        "captured_at_utc": timestamp,
        "sample_rate_hz": sample_rate_hz,
        "sample_count": sample_count,
        "units": dict(CANONICAL_UNITS),
        "quality": {"vibration": "good", "temperature": "good", "rpm": "good"},
        "acceleration_g": samples,
        "temperature_c": temperature_c,
        "rpm": rpm,
        "provenance": {
            "device_family": "esp32",
            "firmware_version": "0.1.0",
            "accelerometer_model": "lab-accelerometer",
            "temperature_sensor_model": "lab-temperature",
            "rpm_sensor_model": "lab-tachometer",
        },
    }


def _build_session(
    root: Path,
    *,
    name: str,
    asset_id: str,
    session_id: str,
    timestamp: str,
    temperature_c: float,
) -> tuple[dict, Path]:
    session = root / name
    session.mkdir()
    capture = session / "capture.jsonl"
    frame = _frame(
        asset_id=asset_id,
        device_id="esp32-lab-01",
        timestamp=timestamp,
        temperature_c=temperature_c,
    )
    capture.write_text(
        json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    rows, report = extract_capture(capture)
    features = session / "features.jsonl"
    feature_report = session / "report.json"
    write_feature_outputs(rows, report, features, feature_report)
    card = create_run_card(features, feature_report, session_id=session_id)
    card_path = session / "card.json"
    write_json(card_path, card)
    return card, card_path


class PhysicalRunCardTests(unittest.TestCase):
    def test_run_card_binds_verified_features_and_preserves_unknown_truth(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            card, _ = _build_session(
                root,
                name="run-a",
                asset_id="PHYS-MTR-01",
                session_id="session-a",
                timestamp="2026-10-31T01:00:00Z",
                temperature_c=31.0,
            )
            validate_run_card(card)
            self.assertTrue(card["card_id"].startswith("physical-run:"))
            self.assertEqual(card["records"], 1)
            self.assertEqual(card["extracted_records"], 1)
            self.assertEqual(card["abstained_records"], 0)
            self.assertEqual(card["calibration_status"], "unverified")
            self.assertEqual(card["label_status"], "unknown")
            self.assertEqual(card["failure_evidence_status"], "unknown")
            self.assertEqual(
                card["publication_status"], "local_only_do_not_redistribute"
            )
            self.assertFalse(card["redistribution_cleared"])
            self.assertFalse(card["training_authorized"])
            self.assertFalse(card["model_scoring_authorized"])
            self.assertFalse(card["diagnosis_authorized"])
            self.assertFalse(card["rul_authorized"])

    def test_card_rejects_feature_tampering_against_report_hash(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "run"
            session.mkdir()
            capture = session / "capture.jsonl"
            frame = _frame(
                asset_id="PHYS-MTR-01",
                device_id="esp32-lab-01",
                timestamp="2026-10-31T01:00:00Z",
                temperature_c=31.0,
            )
            capture.write_text(
                json.dumps(frame, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            rows, report = extract_capture(capture)
            features = session / "features.jsonl"
            report_path = session / "report.json"
            write_feature_outputs(rows, report, features, report_path)
            row = json.loads(features.read_text(encoding="utf-8"))
            row["temperature_c"] = 99.0
            features.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256 does not match report"):
                create_run_card(features, report_path, session_id="session-a")

    def test_card_statuses_cannot_be_promoted_by_editing_json(self):
        with TemporaryDirectory() as tmp:
            card, _ = _build_session(
                Path(tmp),
                name="run-a",
                asset_id="PHYS-MTR-01",
                session_id="session-a",
                timestamp="2026-10-31T01:00:00Z",
                temperature_c=31.0,
            )
            calibration = deepcopy(card)
            calibration["calibration_status"] = "reviewed"
            with self.assertRaisesRegex(ValueError, "cannot promote calibration"):
                validate_run_card(calibration)
            labels = deepcopy(card)
            labels["label_status"] = "known_fault"
            with self.assertRaisesRegex(ValueError, "cannot promote physical labels"):
                validate_run_card(labels)
            evidence = deepcopy(card)
            evidence["failure_evidence_status"] = "observed_failure"
            with self.assertRaisesRegex(ValueError, "cannot promote failure evidence"):
                validate_run_card(evidence)


class PhysicalAssetSplitTests(unittest.TestCase):
    def _cards(self, root: Path) -> tuple[list[dict], list[Path]]:
        specs = [
            ("a-1", "PHYS-MTR-A", "session-a-1", "2026-10-31T01:00:00Z", 30.0),
            ("a-2", "PHYS-MTR-A", "session-a-2", "2026-10-31T02:00:00Z", 31.0),
            ("b-1", "PHYS-MTR-B", "session-b-1", "2026-10-31T03:00:00Z", 32.0),
            ("c-1", "PHYS-MTR-C", "session-c-1", "2026-10-31T04:00:00Z", 33.0),
            ("d-1", "PHYS-MTR-D", "session-d-1", "2026-10-31T05:00:00Z", 34.0),
        ]
        cards: list[dict] = []
        paths: list[Path] = []
        for name, asset, session, timestamp, temperature in specs:
            card, path = _build_session(
                root,
                name=name,
                asset_id=asset,
                session_id=session,
                timestamp=timestamp,
                temperature_c=temperature,
            )
            cards.append(card)
            paths.append(path)
        return cards, paths

    def test_split_keeps_every_session_of_same_asset_in_one_partition(self):
        with TemporaryDirectory() as tmp:
            _, paths = self._cards(Path(tmp))
            plan = asset_split(paths, seed=17)
            self.assertEqual(plan["policy"], "whole_physical_asset_grouped")
            self.assertFalse(plan["training_authorized"])
            self.assertFalse(plan["model_scoring_authorized"])
            asset_partitions: dict[str, str] = {}
            session_partitions: dict[str, str] = {}
            for partition_name, partition in plan["partitions"].items():
                for asset_id in partition["asset_ids"]:
                    self.assertNotIn(asset_id, asset_partitions)
                    asset_partitions[asset_id] = partition_name
                for session_id in partition["session_ids"]:
                    self.assertNotIn(session_id, session_partitions)
                    session_partitions[session_id] = partition_name
            self.assertEqual(
                set(asset_partitions),
                {"PHYS-MTR-A", "PHYS-MTR-B", "PHYS-MTR-C", "PHYS-MTR-D"},
            )
            self.assertEqual(
                session_partitions["session-a-1"], session_partitions["session-a-2"]
            )

    def test_split_is_deterministic_and_input_order_independent(self):
        with TemporaryDirectory() as tmp:
            _, paths = self._cards(Path(tmp))
            first = asset_split(paths, seed=42)
            second = asset_split(list(reversed(paths)), seed=42)
            self.assertEqual(first, second)
            self.assertEqual(first["plan_sha256"], second["plan_sha256"])

    def test_split_rejects_duplicate_sessions_and_feature_content(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, paths = self._cards(root)
            card_b = json.loads(paths[2].read_text(encoding="utf-8"))
            card_b["session_id"] = "session-a-1"
            body = {key: value for key, value in card_b.items() if key != "card_id"}
            canonical = json.dumps(
                body,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            card_b["card_id"] = (
                "physical-run:" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
            )
            duplicate_session = root / "duplicate-session.json"
            duplicate_session.write_text(json.dumps(card_b), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "duplicate physical acquisition session"
            ):
                asset_split([paths[0], paths[1], duplicate_session, paths[3], paths[4]])

            original = json.loads(paths[2].read_text(encoding="utf-8"))
            same_features = deepcopy(original)
            same_features["session_id"] = "session-b-2"
            body = {
                key: value for key, value in same_features.items() if key != "card_id"
            }
            canonical = json.dumps(
                body,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            same_features["card_id"] = (
                "physical-run:" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
            )
            duplicate_features = root / "duplicate-features.json"
            duplicate_features.write_text(json.dumps(same_features), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "duplicate physical feature content"
            ):
                asset_split(
                    [
                        paths[0],
                        paths[1],
                        paths[2],
                        duplicate_features,
                        paths[3],
                        paths[4],
                    ]
                )

    def test_requires_three_distinct_assets(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, paths = self._cards(root)
            with self.assertRaisesRegex(ValueError, "three distinct physical assets"):
                asset_split(paths[:3])

    def test_cli_writes_card_and_split_without_overwrite(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, paths = self._cards(root)
            split_out = root / "split.json"
            arguments = ["split"]
            for path in paths:
                arguments.extend(["--card", str(path)])
            arguments.extend(["--out", str(split_out), "--seed", "9"])
            self.assertEqual(main(arguments), 0)
            document = json.loads(split_out.read_text(encoding="utf-8"))
            self.assertEqual(document["policy"], "whole_physical_asset_grouped")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(arguments)

    def test_documentation_preserves_local_only_no_training_boundary(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_DATASET.md").read_text(encoding="utf-8")
        for phrase in (
            "local-only",
            "does not authorize training",
            "whole physical asset",
            "labels remain unknown",
            "no PLC",
            "no RUL",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
