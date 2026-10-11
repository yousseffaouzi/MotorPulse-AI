"""MP-009: bounded local-only IMS-style ASCII ingestion tests.

All fixture values are handwritten and deliberately NOT actual IMS data.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse.ims import (
    MAX_FILE_BYTES, MAX_FILES, SOURCE_CARD_ID,
    inspect_ims_directory, load_channel_map, write_local_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/ims_style_synthetic"
ONE = "2004.02.12.10.32.39"
TWO = "2004.02.12.10.32.49"


def load(root=FIXTURE, **options):
    kwargs = {
        "test_set": "2", "sample_rate_hz": 8,
        "expected_samples": 4, "expected_channels": 4,
    }
    kwargs.update(options)
    return inspect_ims_directory(root, **kwargs)


class IMSIngestionTests(unittest.TestCase):
    def test_handwritten_fixture_and_correct_channel_features(self):
        result = load()
        self.assertEqual(result["source_card_id"], SOURCE_CARD_ID)
        self.assertEqual(result["test_set"], "2")
        self.assertEqual(result["run_id"], "ims-set-2")
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["channel_record_count"], 8)
        self.assertEqual(result["sample_rate_hz_declared"], 8)
        self.assertEqual(result["snapshot_duration_s"], .5)
        self.assertEqual(result["value_unit_declared"], "unknown")
        self.assertEqual(result["timestamp_timezone"], "unknown")
        first = result["records"][0]
        self.assertEqual(first["filename"], ONE)
        self.assertEqual(first["timestamp_local"], "2004-02-12T10:32:39")
        self.assertIsNone(result["ground_truth"]["window_fault_label"])
        self.assertIsNone(result["ground_truth"]["fault_onset_time"])
        self.assertIsNone(result["ground_truth"]["rul_seconds"])
        ch = first["channels"]
        self.assertEqual(len(ch), 4)
        self.assertAlmostEqual(ch[0]["rms_native"], 1)
        self.assertAlmostEqual(ch[0]["peak_to_peak_native"], 2)
        self.assertAlmostEqual(ch[0]["crest_factor"], 1)
        self.assertAlmostEqual(ch[1]["rms_native"], math.sqrt(30))
        self.assertAlmostEqual(ch[1]["peak_to_peak_native"], 6)
        self.assertEqual(ch[3]["rms_native"], 0)
        self.assertEqual(ch[3]["crest_factor"], 0)
        for row in result["records"]:
            self.assertEqual(len(row["sha256"]), 64)
            self.assertIsNone(row["channels"][0]["bearing_id"])
            self.assertEqual(row["channels"][0]["group_key"], "ims:set-2:ch-01")

    def test_determinism_file_hashes_and_filename_order(self):
        a, b = load(), load()
        self.assertEqual(a, b)
        self.assertEqual([x["filename"] for x in a["records"]], [ONE, TWO])
        import hashlib
        for row in a["records"]:
            self.assertEqual(row["sha256"],
                             hashlib.sha256((FIXTURE / row["filename"]).read_bytes()).hexdigest())
            self.assertEqual(row["bytes"], (FIXTURE / row["filename"]).stat().st_size)

    def test_limit_files_is_oldest_first_and_explicit(self):
        one = load(max_files=1)
        self.assertEqual(one["record_count"], 1)
        self.assertEqual(one["records"][0]["filename"], ONE)

    def test_verified_map_is_explicit_and_provenance_preserved(self):
        mapping = load_channel_map(FIXTURE / "channel-map.json", "2", 4)
        out = load(channel_map=mapping, value_unit="g",
                   archive_sha256="a"*64, acquired_on="2026-10-11")
        self.assertEqual(out["original_archive_sha256"], "a"*64)
        self.assertEqual(out["acquired_on"], "2026-10-11")
        self.assertEqual(out["records"][0]["channels"][0]["bearing_id"], "bearing-1")
        self.assertEqual(out["records"][0]["channels"][0]["value_unit"], "g")
        self.assertEqual(out["channel_mapping"]["source_note"], mapping["source_note"])
        self.assertEqual(out["data_source"], "user_supplied_local_ims_style")

    def test_map_rejects_missing_wrong_or_duplicated_mapping(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "map.json"
            cases = [
                {"test_set":"1","channels":{"1":"bearing-1"},"source_note":"author"},
                {"test_set":"2","channels":{"1":"bearing-1"},"source_note":"author"},
                {"test_set":"2","channels":{str(i):"bearing-"+str(i) for i in range(1,5)},
                 "source_note":""},
                {"test_set":"2","channels":{str(i):"machine-"+str(i) for i in range(1,5)},
                 "source_note":"author"},
            ]
            for bad in cases:
                with self.subTest(bad=bad):
                    file.write_text(json.dumps(bad), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_channel_map(file, "2", 4)
            file.write_text('{"test_set":"2","channels":{},"channels":{},"source_note":"x"}')
            with self.assertRaises(ValueError):
                load_channel_map(file, "2", 4)

    def test_invalid_config_is_rejected_early(self):
        cases = [
            {"test_set":"4"}, {"test_set":1}, {"expected_samples":0},
            {"expected_samples":True}, {"expected_samples":32769},
            {"expected_channels":0}, {"expected_channels":17},
            {"max_files":0}, {"max_files":101}, {"sample_rate_hz":0},
            {"sample_rate_hz":float("nan")}, {"sample_rate_hz":float("inf")},
            {"sample_rate_hz":1_000_001}, {"sample_rate_hz":True},
            {"value_unit":"maybe"}, {"archive_sha256":"invalid"},
            {"archive_sha256":3}, {"acquired_on":"2026-02-30"},
            {"acquired_on":"2026/10/11"}, {"acquired_on":False},
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                load(**args)

    def test_explicit_unit_does_not_infer_unknown_unit(self):
        self.assertEqual(load()["value_unit_declared"], "unknown")
        self.assertEqual(load(value_unit="V")["records"][0]["channels"][0]["value_unit"], "V")

    def test_reject_malformed_rows_header_blank_and_infinity(self):
        with TemporaryDirectory() as tmp:
            record = Path(tmp) / ONE
            for contents in [
                "1 2 3 4\n" * 3,
                "1 2 3 4\n" * 5,
                "1 2 3\n" * 4,
                "1 2 3 4\n\n1 2 3 4\n1 2 3 4\n",
                "a b c d\n" * 4,
                "1 2 nan 4\n" * 4,
                "1 2 inf 4\n" * 4,
                "1 2 1e309 4\n" * 4,
                "1e308 0 0 0\n" * 4,
                "0 0 0 0\n" * 3 + "0 0 0 É\n",
            ]:
                with self.subTest(content=contents[:40]):
                    record.write_text(contents, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load(tmp)

    def test_reject_invalid_calendar_name_and_symlink(self):
        with TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "2004.02.30.10.32.39"
            invalid.write_text("1 2 3 4\n"*4, encoding="ascii")
            with self.assertRaisesRegex(ValueError,"invalid calendar timestamp"):
                load(tmp)
            invalid.unlink()
            if hasattr(os, "symlink"):
                (Path(tmp) / ONE).symlink_to(FIXTURE / ONE)
                with self.assertRaises(ValueError):
                    load(tmp)

    def test_reject_input_directory_and_empty_set(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                load(Path(tmp) / "not_found")
            with self.assertRaisesRegex(ValueError,"no timestamp-named"):
                load(tmp)
            with self.assertRaises(ValueError):
                load(FIXTURE / ONE)
            if hasattr(os, "symlink"):
                alias = Path(tmp) / "alias"
                alias.symlink_to(FIXTURE, target_is_directory=True)
                with self.assertRaises(ValueError):
                    load(alias)

    def test_line_byte_and_record_size_caps(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / ONE
            target.write_text("1 2 3 4\n"*4, encoding="ascii")
            with patch("motorpulse.ims.MAX_FILE_BYTES", 10):
                with self.assertRaisesRegex(ValueError, "file size"):
                    load(tmp)
            target.write_text("1"*2050+"\n")
            with self.assertRaisesRegex(ValueError, "line too long"):
                load(tmp)

    def test_manifest_is_local_deterministic_and_non_overwriting(self):
        report = load()
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "local-report.json"
            write_local_manifest(target, report)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)
            before = target.read_bytes()
            with self.assertRaises(FileExistsError):
                write_local_manifest(target, report)
            self.assertEqual(target.read_bytes(), before)
            with self.assertRaises(ValueError):
                write_local_manifest(Path(tmp) / "new" / "report.json", report)

    def test_cli_with_explicit_rate_and_sample_count(self):
        with TemporaryDirectory() as tmp:
            outfile = Path(tmp) / "report.json"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            args = [sys.executable, "-m", "motorpulse.ims",
                    "--input-dir", str(FIXTURE), "--test-set", "2",
                    "--expected-channels", "4", "--expected-samples", "4",
                    "--sample-rate-hz", "8", "--max-files", "1",
                    "--channel-map", str(FIXTURE / "channel-map.json"),
                    "--manifest", str(outfile)]
            cp = subprocess.run(args, text=True, capture_output=True,
                                cwd=tmp, env=env, timeout=20)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertIn("Validated 1 IMS-style snapshots", cp.stdout)
            report = json.loads(outfile.read_text(encoding="utf-8"))
            self.assertEqual(report["channel_record_count"], 4)
            self.assertEqual(report["records"][0]["channels"][0]["bearing_id"], "bearing-1")
            duplicate = subprocess.run(args, text=True, capture_output=True,
                                       cwd=tmp, env=env, timeout=20)
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("error:", duplicate.stderr)

    def test_cli_requires_explicit_sampling_information(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        cp = subprocess.run([sys.executable, "-m", "motorpulse.ims",
                             "--input-dir", str(FIXTURE), "--test-set", "2"],
                            cwd=ROOT, env=env, text=True,
                            capture_output=True, timeout=20)
        self.assertEqual(cp.returncode, 2)
        self.assertIn("--sample-rate-hz", cp.stderr)
        self.assertIn("--expected-samples", cp.stderr)

    def test_no_archive_or_real_records_embedded_in_fixtures(self):
        fixture_text = (FIXTURE / "README.md").read_text(encoding="utf-8")
        self.assertIn("invented numerical values", fixture_text)
        self.assertIn("not IMS recordings", fixture_text)
        self.assertFalse(any(path.suffix.lower() in {".zip", ".rar", ".7z"}
                             for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    unittest.main()
