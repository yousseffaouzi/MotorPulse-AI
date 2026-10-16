"""MP-031 contracts for a local-only CWRU seeded-bearing-fault adapter.

Fixtures are handwritten MATLAB-v5 bytes; no CWRU measurement is bundled.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from motorpulse.cwru import inspect_cwru_file
from motorpulse.dataset_cards import cwru_run_card, template_card, validate_card


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = "https://engineering.case.edu/bearingdatacenter"


def _element(kind: int, payload: bytes) -> bytes:
    padding = b"\0" * ((-len(payload)) % 8)
    return struct.pack("<II", kind, len(payload)) + payload + padding


def _matrix(name: str, values: list[float], *, array_class: int = 6) -> bytes:
    flags = _element(6, struct.pack("<II", array_class, 0))
    dims = _element(5, struct.pack("<ii", len(values), 1))
    name_part = _element(1, name.encode("ascii"))
    real = _element(9, struct.pack("<" + "d" * len(values), *values))
    return _element(14, flags + dims + name_part + real)


def _write_mat(path: Path, variables: dict[str, list[float]], *, compressed=False) -> None:
    description = b"MATLAB 5.0 MAT-file, handwritten MotorPulse test fixture"
    header = description.ljust(116, b" ") + b"\0" * 8 + struct.pack("<H", 0x0100) + b"IM"
    body = bytearray()
    for name, values in variables.items():
        matrix = _matrix(name, values)
        body.extend(_element(15, zlib.compress(matrix)) if compressed else matrix)
    path.write_bytes(header + bytes(body))


def _metadata(path: Path, **changes) -> dict:
    data = {
        "metadata_version": "1.0.0",
        "source_url": OFFICIAL,
        "file_name": path.name,
        "channel_variable": "X105_DE_time",
        "bearing_location": "drive_end",
        "fault_type": "inner_race",
        "fault_diameter_mils": 7,
        "outer_race_position": None,
        "load_hp": 1,
        "sample_rate_hz": 12000,
        "value_unit": "unknown",
    }
    data.update(changes)
    return data


def _write_metadata(path: Path, data: dict) -> Path:
    metadata = path.with_suffix(".metadata.json")
    metadata.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return metadata


class CWRUMatAdapterTests(unittest.TestCase):
    def test_uncompressed_seeded_fault_summary_and_no_rul(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "105.mat"
            _write_mat(source, {"X105_DE_time": [1.0, -1.0, 2.0, -2.0]})
            metadata = _write_metadata(source, _metadata(source))
            report = inspect_cwru_file(source, metadata)
        self.assertEqual(report["source_card_id"], "cwru-bearing-data-center")
        self.assertEqual(report["series"]["sample_count"], 4)
        self.assertAlmostEqual(report["series"]["rms_native"], (2.5) ** 0.5)
        self.assertEqual(report["labels"]["seeded_fault_type"], "inner_race")
        self.assertEqual(report["labels"]["seeded_fault_diameter_mils"], 7)
        self.assertFalse(report["labels"]["run_to_failure"])
        self.assertIsNone(report["labels"]["failure_time"])
        self.assertIsNone(report["labels"]["remaining_useful_life"])

    def test_compressed_normal_file_preserves_normal_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "97.mat"
            _write_mat(source, {"X097_DE_time": [0.0, 0.5, -0.5, 0.0]}, compressed=True)
            metadata = _write_metadata(
                source,
                _metadata(
                    source,
                    channel_variable="X097_DE_time",
                    fault_type="normal",
                    fault_diameter_mils=None,
                ),
            )
            report = inspect_cwru_file(source, metadata)
        self.assertEqual(report["labels"]["seeded_fault_type"], "normal")
        self.assertIsNone(report["labels"]["seeded_fault_diameter_mils"])
        self.assertEqual(report["metadata"]["experiment_type"], "seeded_fault_not_run_to_failure")

    def test_channel_and_fault_metadata_are_explicit_not_filename_inferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "mystery.mat"
            _write_mat(
                source,
                {
                    "X105_DE_time": [1.0, 2.0, 3.0, 4.0],
                    "X105_FE_time": [9.0, 9.0, 9.0, 9.0],
                },
            )
            metadata = _write_metadata(source, _metadata(source))
            report = inspect_cwru_file(source, metadata)
        self.assertEqual(report["source_file_name"], "mystery.mat")
        self.assertEqual(report["metadata"]["channel_variable"], "X105_DE_time")
        self.assertNotIn("X105_FE_time", json.dumps(report))

    def test_metadata_validation_matches_documented_seeded_experiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "x.mat"
            _write_mat(source, {"X105_DE_time": [1.0, 2.0]})
            base = _metadata(source)
            invalid = (
                {**base, "source_url": "https://example.com/copy"},
                {**base, "file_name": "other.mat"},
                {**base, "sample_rate_hz": 20000},
                {**base, "load_hp": 4},
                {**base, "fault_diameter_mils": 13},
                {**base, "fault_type": "normal", "fault_diameter_mils": 7},
                {**base, "fault_type": "outer_race", "outer_race_position": None},
                {**base, "fault_type": "inner_race", "outer_race_position": "6_oclock"},
            )
            for index, document in enumerate(invalid):
                metadata = _write_metadata(source, document)
                with self.subTest(index=index), self.assertRaises(ValueError):
                    inspect_cwru_file(source, metadata)

    def test_mat_reader_rejects_symlink_truncation_and_non_double_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "x.mat"
            _write_mat(source, {"X105_DE_time": [1.0, 2.0]})
            metadata = _write_metadata(source, _metadata(source))
            link = root / "link.mat"
            try:
                link.symlink_to(source)
            except OSError:
                link = None
            if link is not None:
                linked_meta = _write_metadata(link, _metadata(link))
                with self.assertRaises(ValueError):
                    inspect_cwru_file(link, linked_meta)
            source.write_bytes(source.read_bytes()[:140])
            with self.assertRaises(ValueError):
                inspect_cwru_file(source, metadata)
            bad = root / "bad.mat"
            description = b"MATLAB 5.0 MAT-file, handwritten MotorPulse test fixture"
            header = description.ljust(116, b" ") + b"\0" * 8 + struct.pack("<H", 0x0100) + b"IM"
            bad.write_bytes(header + _matrix("X105_DE_time", [1.0, 2.0], array_class=7))
            bad_meta = _write_metadata(bad, _metadata(bad))
            with self.assertRaises(ValueError):
                inspect_cwru_file(bad, bad_meta)

    def test_report_is_summary_only_without_raw_samples_or_local_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "105.mat"
            _write_mat(source, {"X105_DE_time": [1.0, -1.0, 2.0, -2.0]})
            metadata = _write_metadata(source, _metadata(source))
            report = inspect_cwru_file(source, metadata)
            encoded = json.dumps(report, sort_keys=True)
        self.assertNotIn(str(source.parent), encoded)
        self.assertNotIn("samples", report["series"])
        self.assertEqual(len(report["source_file_sha256"]), 64)
        self.assertEqual(report["rights"]["publication_status"], "local_only_do_not_redistribute")

    def test_cli_is_write_once_and_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "105.mat"
            _write_mat(source, {"X105_DE_time": [1.0, -1.0, 2.0, -2.0]})
            metadata = _write_metadata(source, _metadata(source))
            out = root / "report.json"
            command = [
                sys.executable,
                "-m",
                "motorpulse.cwru",
                "--input",
                str(source),
                "--metadata",
                str(metadata),
                "--out",
                str(out),
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(report["source_card_id"], "cwru-bearing-data-center")


class CWRUDocumentationAndCardTests(unittest.TestCase):
    def test_packaged_card_is_local_only_and_seeded_not_run_to_failure(self):
        card = template_card("cwru")
        validate_card(card)
        self.assertEqual(card["dataset_type"], "user_supplied_local_cwru_seeded_fault")
        self.assertEqual(card["publication_status"], "local_only_do_not_redistribute")
        self.assertIn("seeded", card["labels"]["notes"].lower())
        self.assertIsNone(card["labels"]["remaining_useful_life"])

    def test_run_card_uses_summary_provenance_without_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "105.mat"
            _write_mat(source, {"X105_DE_time": [1.0, -1.0, 2.0, -2.0]})
            metadata = _write_metadata(source, _metadata(source))
            report_path = root / "report.json"
            report_path.write_text(
                json.dumps(inspect_cwru_file(source, metadata), sort_keys=True),
                encoding="utf-8",
            )
            card = cwru_run_card(report_path)
        validate_card(card)
        self.assertEqual(card["run_provenance"]["fault_type"], "inner_race")
        self.assertFalse(card["run_provenance"]["run_to_failure"])
        self.assertNotIn("rms_native", json.dumps(card))

    def test_docs_source_card_and_entrypoint_preserve_rights_uncertainty(self):
        guide = (ROOT / "docs" / "CWRU_INGESTION.md").read_text(encoding="utf-8")
        source = json.loads(
            (ROOT / "docs" / "sources" / "cwru-bearings.source.json").read_text(
                encoding="utf-8"
            )
        )
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("motorpulse-cwru", pyproject)
        for term in (
            OFFICIAL,
            "https://engineering.case.edu/bearingdatacenter/download-data-file",
            "seeded",
            "EDM",
            "not run-to-failure",
            "redistribution",
            "local-only",
        ):
            with self.subTest(term=term):
                self.assertIn(term, guide)
        self.assertEqual(source["rights_status"], "unverified_for_redistribution")
        self.assertFalse(source["raw_or_derived_data_in_repository"])


if __name__ == "__main__":
    unittest.main()
