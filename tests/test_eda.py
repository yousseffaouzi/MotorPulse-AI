"""MP-029: deterministic exploratory summaries, provenance and safe report outputs.

All source data are synthetic or hand-authored fixtures; no third-party IMS
files or derived data are ever committed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from motorpulse.config_file import load_config_file
from motorpulse.eda import (
    MAX_TREND_POINTS, ims_quality_report, render_markdown, save_report,
    synthetic_quality_report,
)
from motorpulse.export import export_dataset
from motorpulse.ims import inspect_ims_directory, write_local_manifest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/ims_style_synthetic"


def ims():
    return inspect_ims_directory(FIXTURE, test_set="2", sample_rate_hz=8,
                                 expected_samples=4, expected_channels=4)


class SyntheticEDATests(unittest.TestCase):
    def test_manifest_and_descriptive_statistics(self):
        with TemporaryDirectory() as root:
            folder = Path(root) / "data"
            manifest = export_dataset(folder, ticks=4, seed=12)
            report = synthetic_quality_report(folder)
            self.assertTrue(report["synthetic_only"])
            self.assertEqual(report["export_id"], manifest["export_id"])
            self.assertEqual(report["events"], 12)
            self.assertEqual(report["ticks"], 4)
            self.assertEqual(report["assets"], 3)
            self.assertEqual(len(report["per_asset"]), 3)
            self.assertEqual(report["source_file_sha256"],
                             manifest["files"]["events.jsonl"]["sha256"])
            self.assertEqual(report["sample_rate_hz"], 1024)
            for group in report["per_asset"].values():
                self.assertEqual(group["observations"], 4)
                self.assertEqual(sum(group["synthetic_fault_truth_counts"].values()), 4)
                self.assertEqual(sum(group["sensor_quality_counts"].values()), 4)
                self.assertEqual(sum(group["heuristic_health_counts"].values()), 4)
                for stats in group["features"].values():
                    self.assertEqual(stats["count"], 4)
                    self.assertEqual(stats["missing_count"], 0)
                    self.assertLessEqual(stats["min"], stats["median"])
                    self.assertLessEqual(stats["median"], stats["max"])
                self.assertEqual(len(group["trend_sample_first_last"]), 4)

    def test_determinism_across_dirs_and_creation_time(self):
        with TemporaryDirectory() as root:
            export_dataset(Path(root) / "a", ticks=5, seed=8)
            export_dataset(Path(root) / "b", ticks=5, seed=8)
            a = synthetic_quality_report(Path(root) / "a")
            b = synthetic_quality_report(Path(root) / "b")
            self.assertEqual(a, b)
            self.assertNotIn("created_at_utc", a)
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
            self.assertEqual(render_markdown(a), render_markdown(b))

    def test_missing_sensor_is_not_zero_and_outlier_is_suspect(self):
        assets = load_config_file(ROOT / "docs/examples/operations-v1.json")
        with TemporaryDirectory() as root:
            export_dataset(Path(root) / "a", ticks=8, assets=assets)
            summary = synthetic_quality_report(Path(root) / "a")
            pump = summary["per_asset"]["MTR-02"]
            self.assertEqual(pump["sensor_quality_counts"]["missing"], 2)
            self.assertEqual(pump["heuristic_health_counts"]["unavailable"], 2)
            self.assertEqual(pump["features"]["rms_g"]["missing_count"], 2)
            self.assertEqual(pump["features"]["rms_g"]["count"], 6)
            self.assertEqual(pump["features"]["temperature_c"]["missing_count"], 0)
            fan = summary["per_asset"]["MTR-03"]
            self.assertEqual(fan["sensor_quality_counts"]["outlier"], 1)
            self.assertEqual(fan["heuristic_health_counts"]["suspect"], 1)
            self.assertIn("healthy", fan["synthetic_fault_truth_counts"])
            self.assertIsNone(next(x for x in pump["trend_sample_first_last"]
                                   if x["tick"] == 5)["rms_g"])

    def test_bounded_trend_first_last_and_provenance(self):
        with TemporaryDirectory() as root:
            export_dataset(Path(root) / "a", ticks=20)
            report = synthetic_quality_report(Path(root) / "a")
            for group in report["per_asset"].values():
                trend = group["trend_sample_first_last"]
                self.assertEqual(len(trend), MAX_TREND_POINTS)
                self.assertEqual([x["tick"] for x in trend],
                                 list(range(1,7)) + list(range(15,21)))
            self.assertIn("programmed synthetic", report["label_note"])

    def test_tampered_jsonl_or_csv_checksum_is_rejected(self):
        with TemporaryDirectory() as root:
            folder = Path(root) / "a"
            export_dataset(folder, ticks=2)
            file = folder / "events.jsonl"
            file.write_bytes(file.read_bytes().replace(b'"normal"',b'"critical"',1))
            with self.assertRaisesRegex(ValueError, "integrity check"):
                synthetic_quality_report(folder)
            folder2 = Path(root) / "b"
            export_dataset(folder2, ticks=2)
            csv = folder2 / "events.csv"
            csv.write_bytes(csv.read_bytes() + b"bad extra line\n")
            with self.assertRaisesRegex(ValueError, "integrity check"):
                synthetic_quality_report(folder2)

    def test_csv_only_and_missing_manifest_are_rejected(self):
        with TemporaryDirectory() as root:
            csv = Path(root) / "csv"
            export_dataset(csv, ticks=1, file_format="csv")
            with self.assertRaisesRegex(ValueError, "events.jsonl"):
                synthetic_quality_report(csv)
            with self.assertRaises(ValueError):
                synthetic_quality_report(Path(root) / "missing")

    def test_invalid_or_duplicate_jsonl_event_rejected_with_valid_hash(self):
        with TemporaryDirectory() as root:
            folder = Path(root) / "a"
            export_dataset(folder, ticks=2, file_format="jsonl")
            events = folder / "events.jsonl"
            manifest_path = folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            lines = events.read_text(encoding="utf-8").splitlines()
            lines[1] = lines[0]
            payload = ("\n".join(lines) + "\n").encode()
            events.write_bytes(payload)
            manifest["files"]["events.jsonl"]["bytes"] = len(payload)
            manifest["files"]["events.jsonl"]["sha256"] = hashlib.sha256(payload).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                synthetic_quality_report(folder)

    def test_unsupported_data_source_fails(self):
        with TemporaryDirectory() as root:
            folder = Path(root) / "a"
            export_dataset(folder, ticks=1)
            manifest_path = folder / "manifest.json"
            meta = json.loads(manifest_path.read_text(encoding="utf-8"))
            meta["synthetic_only"] = False
            manifest_path.write_text(json.dumps(meta),encoding="utf-8")
            with self.assertRaises(ValueError):
                synthetic_quality_report(folder)



    def test_all_vibration_missing_has_null_statistics(self):
        from motorpulse.scenarios import AssetScenario
        motor = AssetScenario(
            "MTR-01", "Missing signal", scenario="healthy", severity=0,
            sensor_missing_onset_tick=1, sensor_missing_duration_ticks=4,
        )
        with TemporaryDirectory() as root:
            folder = Path(root) / "data"
            export_dataset(folder, ticks=4, assets=(motor,))
            summary = synthetic_quality_report(folder)["per_asset"]["MTR-01"]
            stats = summary["features"]["rms_g"]
            self.assertEqual(stats["count"], 0)
            self.assertEqual(stats["missing_count"], 4)
            self.assertIsNone(stats["mean"])
            self.assertIsNone(stats["median"])
            self.assertEqual(summary["features"]["temperature_c"]["count"], 4)

    def test_percentile_interpolation_and_population_deviation(self):
        from motorpulse.eda import _describe
        stats = _describe([7, 1, 5, 3], 5)
        self.assertEqual(stats["count"], 4)
        self.assertEqual(stats["missing_count"], 1)
        self.assertEqual(stats["mean"], 4)
        self.assertEqual(stats["median"], 4)
        self.assertAlmostEqual(stats["p05"], 1.3)
        self.assertAlmostEqual(stats["p95"], 6.7)
        self.assertAlmostEqual(stats["std"], 5**0.5)


class LocalIMSEDATests(unittest.TestCase):
    def test_ims_summary_has_unknown_fault_labels_and_quality_flags(self):
        source = ims()
        report = ims_quality_report(source)
        self.assertFalse(report["synthetic_only"])
        self.assertEqual(report["run_id"], "ims-set-2")
        self.assertEqual(report["record_count"], 2)
        self.assertEqual(report["channel_record_count"], 8)
        self.assertEqual(len(report["per_channel"]), 4)
        self.assertEqual(report["timestamp_timezone"], "unknown; no UTC conversion")
        self.assertEqual(report["ground_truth"]["window_fault_label"], None)
        self.assertIsNone(report["ground_truth"]["fault_onset_time"])
        self.assertIsNone(report["ground_truth"]["rul_seconds"])
        self.assertEqual(report["verification"]["issues_by_code"]["unit_unverified"], 8)
        self.assertEqual(report["verification"]["issues_by_code"]["bearing_mapping_unverified"], 8)
        self.assertEqual(report["per_channel"]["ims:set-2:ch-01"]["features"]["rms_native"]["count"], 2)
        self.assertEqual(report["value_unit_declared"], "unknown")

    def test_ims_reverify_files_and_review_cadence(self):
        result = ims_quality_report(ims(), verify_files=True, expected_interval_s=20)
        self.assertTrue(result["verification"]["file_hashes_rechecked"])
        self.assertEqual(result["verification"]["issues_by_code"]["cadence_deviation"], 1)
        self.assertEqual(result["per_channel"]["ims:set-2:ch-01"]["trend_sample_first_last"][0]["timestamp_local"],
                         "2004-02-12T10:32:39")

    def test_ims_mutation_rejected(self):
        source = ims()
        modified = copy.deepcopy(source)
        modified["ground_truth"]["window_fault_label"] = "fault"
        with self.assertRaises(ValueError):
            ims_quality_report(modified)
        modified = copy.deepcopy(source)
        modified["value_unit_declared"] = "g"
        with self.assertRaises(ValueError):
            ims_quality_report(modified)

    def test_ims_summaries_replay_and_do_not_mutate_input(self):
        source = ims()
        frozen = json.dumps(source, sort_keys=True)
        a,b = ims_quality_report(source),ims_quality_report(source)
        self.assertEqual(a,b)
        self.assertEqual(frozen,json.dumps(source,sort_keys=True))
        markdown = render_markdown(a)
        self.assertIn("unknown",markdown)
        self.assertIn("local_only_do_not_redistribute",markdown)
        self.assertIn("rms_native",markdown)
        self.assertNotIn("synthetic_fault_truth_counts",markdown)


class OutputAndCLITests(unittest.TestCase):
    def test_write_json_markdown_and_exclusive_output(self):
        with TemporaryDirectory() as root:
            report = ims_quality_report(ims())
            json_file = Path(root) / "one.json"
            markdown_file = Path(root) / "one.md"
            save_report(json_file,report)
            save_report(markdown_file,report,output_format="markdown")
            self.assertEqual(json.loads(json_file.read_text(encoding="utf-8")), report)
            self.assertIn("## Per-channel summary",markdown_file.read_text(encoding="utf-8"))
            self.assertTrue(markdown_file.read_bytes().endswith(b"\n"))
            before = markdown_file.read_bytes()
            with self.assertRaises(FileExistsError):
                save_report(markdown_file,report,output_format="markdown")
            self.assertEqual(markdown_file.read_bytes(),before)

    def test_output_rejects_missing_parent_and_bad_format(self):
        with TemporaryDirectory() as root:
            report = ims_quality_report(ims())
            target = Path(root) / "missing" / "report.json"
            with self.assertRaises(ValueError):
                save_report(target,report)
            with self.assertRaises(ValueError):
                save_report(Path(root) / "file.txt",report,output_format="html")

    def test_cli_synthetic_and_ims_roundtrip(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            dataset = root / "synthetic"
            export_dataset(dataset,ticks=3)
            inspected = root / "ims-inspect.json"
            write_local_manifest(inspected,ims())
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            for source, incoming, filename, fmt in (
                ("synthetic", dataset, "synthetic.json", "json"),
                ("ims", inspected, "ims.md", "markdown"),
            ):
                with self.subTest(source=source):
                    result = subprocess.run([
                        sys.executable,"-m","motorpulse.eda",
                        "--source",source,"--input",str(incoming),
                        "--out",str(root / filename),"--format",fmt,
                    ],env=env,cwd=root,text=True,capture_output=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertTrue((root / filename).exists())
            invalid = subprocess.run([
                sys.executable,"-m","motorpulse.eda",
                "--source","ims","--input",str(inspected),
                "--out",str(root / "ims.md"),"--format","markdown",
            ],env=env,cwd=root,text=True,capture_output=True,timeout=30)
            self.assertEqual(invalid.returncode,2)
            self.assertIn("error:",invalid.stderr)

    def test_cli_rejects_ims_flags_for_synthetic(self):
        with TemporaryDirectory() as root:
            root=Path(root)
            export_dataset(root / "synthetic",ticks=1)
            env=dict(os.environ); env["PYTHONPATH"]=str(ROOT)
            result=subprocess.run([
                sys.executable,"-m","motorpulse.eda",
                "--source","synthetic","--input",str(root / "synthetic"),
                "--verify-files","--out",str(root / "bad.json"),
            ],env=env,cwd=root,text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,2)
            self.assertFalse((root / "bad.json").exists())


if __name__ == "__main__":
    unittest.main()
