"""MP-008: bounded deterministic CSV/JSONL export and manifest contracts."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse.config_file import load_config_file
from motorpulse.export import EXPORT_FIELDS, MAX_EXPORT_TICKS, export_dataset
from motorpulse.schema import SCHEMA_VERSION, validate_snapshot
from motorpulse.sim import MotorSimulator

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fp:
        return [json.loads(line) for line in fp]


class DatasetExportTests(unittest.TestCase):
    def test_jsonl_and_csv_roundtrip_metadata_checksums(self):
        with TemporaryDirectory() as root:
            output = Path(root) / "dataset"
            manifest = export_dataset(output, ticks=3, seed=71)
            self.assertEqual(manifest["events"], 9)
            self.assertEqual(manifest["ticks"], 3)
            self.assertTrue(manifest["synthetic_only"])
            self.assertEqual(manifest["schema_version"], SCHEMA_VERSION)
            self.assertEqual(manifest["sample_rate_hz"], 1024)
            self.assertEqual(len(manifest["model_source_sha256"]), 64)
            self.assertIn("sim.py", manifest["source_filenames"])
            self.assertEqual(manifest["format"], "both")
            self.assertEqual(tuple(manifest["columns"]), EXPORT_FIELDS)
            self.assertEqual(manifest["virtual_start_utc"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(manifest["virtual_end_utc"], "2026-01-01T00:00:03+00:00")
            self.assertEqual(json.loads((output / "manifest.json").read_text()), manifest)
            self.assertIn("created_at_utc", manifest)
            self.assertIsNotNone(datetime.fromisoformat(manifest["created_at_utc"]))
            self.assertEqual(set(manifest["files"]), {"events.csv", "events.jsonl"})

            events = read_jsonl(output / "events.jsonl")
            self.assertEqual(len(events), 9)
            self.assertEqual([x["tick"] for x in events], [1]*3 + [2]*3 + [3]*3)
            self.assertTrue(all(x["export_id"] == manifest["export_id"] for x in events))
            self.assertTrue(all(set(x) == set(EXPORT_FIELDS) for x in events))
            self.assertEqual(len({x["event_id"] for x in events}), 9)
            with (output / "events.csv").open(newline="", encoding="utf-8") as fp:
                reader = csv.DictReader(fp)
                self.assertEqual(tuple(reader.fieldnames), EXPORT_FIELDS)
                table = list(reader)
            self.assertEqual(len(table), len(events))
            for row, event in zip(table, events):
                self.assertEqual(row["tick"], str(event["tick"]))
                self.assertEqual(row["asset_id"], event["asset_id"])
                self.assertEqual(row["event_id"], event["event_id"])
                self.assertEqual(json.loads(row["units"]), event["units"])
                self.assertEqual(json.loads(row["reasons"]), event["reasons"])
                self.assertEqual(json.loads(row["operating_config"]), event["operating_config"])
            for filename, metadata in manifest["files"].items():
                data = (output / filename).read_bytes()
                self.assertEqual(metadata["bytes"], len(data))
                self.assertEqual(metadata["sha256"], hashlib.sha256(data).hexdigest())

    def test_export_data_bytes_are_identical_across_output_paths(self):
        with TemporaryDirectory() as root:
            a = export_dataset(Path(root) / "a", ticks=4, seed=7)
            b = export_dataset(Path(root) / "b", ticks=4, seed=7)
            self.assertEqual(a["export_id"], b["export_id"])
            self.assertEqual(a["config_sha256"], b["config_sha256"])
            self.assertEqual(a["files"], b["files"])
            for filename in ("events.csv", "events.jsonl"):
                self.assertEqual((Path(root) / "a" / filename).read_bytes(),
                                 (Path(root) / "b" / filename).read_bytes())
            self.assertEqual(a["virtual_start_utc"], b["virtual_start_utc"])
            self.assertEqual(a["events"], b["events"])
            # created_at_utc is deliberately excluded from data files; it is
            # actual wall-clock metadata and is not guaranteed deterministic.

    def test_missing_and_outlier_labels_and_csv_blanks(self):
        assets = load_config_file(ROOT / "docs/examples/operations-v1.json")
        with TemporaryDirectory() as root:
            output = Path(root) / "events"
            manifest = export_dataset(output, ticks=7, seed=42, assets=assets)
            self.assertEqual(manifest["events"], 21)
            records = read_jsonl(output / "events.jsonl")
            missing = next(row for row in records
                           if row["asset_id"] == "MTR-02" and row["tick"] == 5)
            self.assertEqual(missing["sensor_quality"], "missing")
            self.assertEqual(missing["health"], "unavailable")
            self.assertIsNone(missing["rms_g"])
            self.assertIsNone(missing["rolling_rms_mean_g"])
            self.assertEqual(missing["configured_scenario"], "bearing_wear")
            outlier = next(row for row in records
                           if row["asset_id"] == "MTR-03" and row["tick"] == 4)
            self.assertEqual(outlier["sensor_quality"], "outlier")
            self.assertEqual(outlier["health"], "suspect")
            self.assertIsInstance(outlier["rms_g"], float)
            with (output / "events.csv").open(newline="", encoding="utf-8") as fp:
                rows = list(csv.DictReader(fp))
            csv_missing = next(row for row in rows
                               if row["asset_id"] == "MTR-02" and row["tick"] == "5")
            self.assertEqual(csv_missing["rms_g"], "")
            self.assertEqual(csv_missing["crest_factor"], "")
            self.assertEqual(csv_missing["sensor_quality"], "missing")
            self.assertEqual(csv_missing["health"], "unavailable")

    def test_export_matches_simulator_exactly_without_mutation(self):
        with TemporaryDirectory() as root:
            manifest = export_dataset(Path(root) / "a", ticks=2, seed=19)
            events = read_jsonl(Path(root) / "a" / "events.jsonl")
            sim = MotorSimulator(seed=19)
            expected = []
            for _ in range(2):
                snap = sim.step()
                validate_snapshot(snap)
                for motor in snap["assets"]:
                    expected.append({
                        "export_id": manifest["export_id"],
                        "schema_version": snap["schema_version"],
                        "tick": snap["tick"],
                        "recorded_at_utc": snap["recorded_at_utc"],
                        **motor,
                    })
            self.assertEqual(events, expected)

    def test_csv_only_and_jsonl_only(self):
        with TemporaryDirectory() as root:
            csv_meta = export_dataset(Path(root) / "csv", ticks=1, file_format="csv")
            json_meta = export_dataset(Path(root) / "json", ticks=1, file_format="jsonl")
            self.assertEqual(csv_meta["export_id"], json_meta["export_id"])
            self.assertEqual(set(csv_meta["files"]), {"events.csv"})
            self.assertEqual(set(json_meta["files"]), {"events.jsonl"})
            self.assertFalse((Path(root) / "csv" / "events.jsonl").exists())
            self.assertFalse((Path(root) / "json" / "events.csv").exists())

    def test_existing_output_is_never_overwritten(self):
        with TemporaryDirectory() as root:
            out = Path(root) / "dataset"
            first = export_dataset(out, ticks=1)
            old = (out / "events.jsonl").read_bytes()
            with self.assertRaises(FileExistsError):
                export_dataset(out, ticks=5)
            self.assertEqual((out / "events.jsonl").read_bytes(), old)
            self.assertEqual(json.loads((out / "manifest.json").read_text()), first)
            existing_file = Path(root) / "existing"
            existing_file.write_text("KEEP", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_dataset(existing_file, ticks=1)
            self.assertEqual(existing_file.read_text(), "KEEP")

    def test_invalid_settings_do_not_create_destination(self):
        with TemporaryDirectory() as root:
            output = Path(root) / "not-created"
            for kwargs in (
                {"ticks": 0}, {"ticks": -1}, {"ticks": MAX_EXPORT_TICKS + 1},
                {"ticks": True}, {"ticks": 2.0}, {"ticks": 1, "file_format": "parquet"},
                {"ticks": 1, "seed": "x"}, {"ticks": 1, "step_seconds": 0},
                {"ticks": 1, "start_time_utc": datetime(9999, 12, 31, 23, 59, 59,
                                                       tzinfo=timezone.utc),
                 "step_seconds": 86400, "ticks": 2},
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    export_dataset(output, **kwargs)
                self.assertFalse(output.exists())
            with self.assertRaises(ValueError):
                export_dataset(output / "nested", ticks=1)
            self.assertFalse(output.exists())

    def test_size_limit_failure_cleans_up_only_new_directory(self):
        with TemporaryDirectory() as root:
            destination = Path(root) / "new"
            sentinel = Path(root) / "keep.txt"
            sentinel.write_text("unchanged", encoding="utf-8")
            with patch("motorpulse.export.MAX_DATA_BYTES", 1):
                with self.assertRaises(ValueError):
                    export_dataset(destination, ticks=1)
            self.assertFalse(destination.exists())
            self.assertEqual(sentinel.read_text(), "unchanged")

    def test_csv_formula_safe_name_and_unicode_jsonl(self):
        from motorpulse.scenarios import AssetScenario
        assets = (AssetScenario("MTR-01", '=SUM(A1:A2) – résumé'),)
        with TemporaryDirectory() as root:
            output = Path(root) / "formula"
            export_dataset(output, ticks=1, assets=assets)
            item = read_jsonl(output / "events.jsonl")[0]
            self.assertEqual(item["name"], "=SUM(A1:A2) – résumé")
            with (output / "events.csv").open(newline="", encoding="utf-8") as fp:
                csv_item = next(csv.DictReader(fp))
            self.assertEqual(csv_item["name"], "'=SUM(A1:A2) – résumé")

    def test_cli_subprocess_from_other_working_directory(self):
        with TemporaryDirectory() as root:
            work = Path(root)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            args = [sys.executable, "-m", "motorpulse.export",
                    "--out-dir", "exported", "--config",
                    str(ROOT / "docs/examples/operations-v1.json"),
                    "--ticks", "2", "--format", "jsonl",
                    "--seed", "24", "--step-seconds", "2"]
            process = subprocess.run(args, cwd=work, env=env, text=True,
                                     capture_output=True, timeout=30, check=False)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("Exported 6 synthetic events", process.stdout)
            manifest = json.loads((work / "exported" / "manifest.json").read_text())
            self.assertEqual(manifest["seed"], 24)
            self.assertEqual(manifest["events"], 6)
            self.assertEqual(set(manifest["files"]), {"events.jsonl"})
            fail = subprocess.run(args, cwd=work, env=env, text=True,
                                  capture_output=True, timeout=30, check=False)
            self.assertEqual(fail.returncode, 2)
            self.assertIn("error:", fail.stderr)

    def test_csv_jsonl_are_utf8_newline_delimited(self):
        with TemporaryDirectory() as root:
            output = Path(root) / "a"
            export_dataset(output, ticks=1)
            for name in ("events.csv", "events.jsonl"):
                body = (output / name).read_bytes()
                self.assertTrue(body.endswith(b"\n"))
                self.assertNotIn(b"\r\n", body)
                self.assertFalse(body.startswith(b"\xef\xbb\xbf"))
                body.decode("utf-8")

    def test_export_id_changes_when_data_configuration_changes(self):
        with TemporaryDirectory() as root:
            a = export_dataset(Path(root) / "a", ticks=1, seed=1)
            b = export_dataset(Path(root) / "b", ticks=1, seed=2)
            c = export_dataset(Path(root) / "c", ticks=2, seed=1)
            self.assertNotEqual(a["export_id"], b["export_id"])
            self.assertNotEqual(a["export_id"], c["export_id"])


if __name__ == "__main__":
    unittest.main()
