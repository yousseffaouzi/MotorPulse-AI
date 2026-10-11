"""MP-028: locally generated IMS-style validation and leakage guard tests."""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from motorpulse.ims import inspect_ims_directory, write_local_manifest
from motorpulse.ims_validation import (
    FEATURE_KEYS, fit_train_scaler, transform_report, validate_ims_report,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/ims_style_synthetic"


def report(set_id="2", *, unit="unknown", rate=8):
    return inspect_ims_directory(
        FIXTURE, test_set=set_id, sample_rate_hz=rate,
        expected_samples=4, expected_channels=4, value_unit=unit)


class ReportValidationTests(unittest.TestCase):
    def test_handwritten_report_review_flags_are_not_diagnoses(self):
        result = validate_ims_report(report())
        self.assertEqual(result["run_id"], "ims-set-2")
        self.assertEqual(result["source_report_record_count"], 2)
        self.assertEqual(result["channel_record_count"], 8)
        self.assertFalse(result["verified_file_checksums"])
        self.assertEqual(result["counts_by_issue"]["unit_unverified"], 8)
        self.assertEqual(result["counts_by_issue"]["bearing_mapping_unverified"], 8)
        self.assertGreaterEqual(result["counts_by_issue"]["flatline_review"], 2)
        self.assertIn("not failure labels", result["diagnostic_claims"])
        self.assertEqual(result["timestamp_timezone"], "unknown")
        self.assertEqual(result["publication_status"], "local_only_do_not_redistribute")

    def test_file_verification_and_provenance(self):
        checked = validate_ims_report(report(), verify_files=True)
        self.assertTrue(checked["verified_file_checksums"])
        self.assertEqual(checked["sample_rate_hz_declared"], 8.0)
        self.assertEqual(checked["value_unit_declared"], "unknown")

    def test_modified_source_files_rejected_by_hash_check(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ("2004.02.12.10.32.39", "2004.02.12.10.32.49"):
                shutil.copyfile(FIXTURE / name, folder / name)
            source = inspect_ims_directory(folder, test_set="2", sample_rate_hz=8,
                                           expected_samples=4, expected_channels=4)
            validate_ims_report(source, verify_files=True)
            target = folder / "2004.02.12.10.32.39"
            text = target.read_text(encoding="ascii").replace("1\t2", "2\t2", 1)
            target.write_text(text, encoding="ascii")
            with self.assertRaisesRegex(ValueError, "checksum/size mismatch"):
                validate_ims_report(source, verify_files=True)

    def test_strict_chronology_duplicate_and_cadence(self):
        data = report()
        result = validate_ims_report(data, expected_interval_s=20)
        self.assertEqual(result["counts_by_issue"]["cadence_deviation"], 1)
        self.assertNotIn("window_overlap", result["counts_by_issue"])
        invalid = copy.deepcopy(data)
        invalid["records"].reverse()
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            validate_ims_report(invalid)
        duplicate = copy.deepcopy(data)
        duplicate["records"][1] = copy.deepcopy(duplicate["records"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_ims_report(duplicate)

    def test_close_timestamps_are_flagged_not_converted_to_utc(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            shutil.copyfile(FIXTURE / "2004.02.12.10.32.39", folder / "2004.02.12.10.32.39")
            shutil.copyfile(FIXTURE / "2004.02.12.10.32.49", folder / "2004.02.12.10.32.40")
            data = inspect_ims_directory(folder, test_set="2", sample_rate_hz=1,
                                         expected_samples=4, expected_channels=4)
            result = validate_ims_report(data)
            self.assertEqual(result["counts_by_issue"]["window_overlap"], 1)
            self.assertEqual(result["timestamp_timezone"], "unknown")

    def test_schema_mismatches_rejected(self):
        original = report()
        changes = [
            ("record_count", 99),
            ("channel_record_count", 99),
            ("sample_rate_hz_declared", 0),
            ("snapshot_duration_s", 9),
            ("timestamp_timezone", "UTC"),
            ("publication_status", "public"),
            ("run_id", "ims-set-1"),
            ("value_unit_declared", "g"),
        ]
        for key, value in changes:
            with self.subTest(key=key):
                data = copy.deepcopy(original)
                data[key] = value
                with self.assertRaises(ValueError):
                    validate_ims_report(data)

    def test_channel_mismatch_numeric_and_unit_rejection(self):
        data = report()
        for field, bad in (
            ("rms_native", float("nan")),
            ("rms_native", -1),
            ("peak_to_peak_native", float("inf")),
            ("crest_factor", -1),
            ("channel_id", "ch-09"),
            ("group_key", "other-run"),
            ("value_unit", "V"),
            ("bearing_id", "bearing-1"),
        ):
            with self.subTest(field=field):
                broken = copy.deepcopy(data)
                broken["records"][0]["channels"][0][field] = bad
                with self.assertRaises(ValueError):
                    validate_ims_report(broken)

    def test_bearing_ids_remain_unknown_without_explicit_map(self):
        data = report()
        self.assertTrue(all(ch["bearing_id"] is None for rec in data["records"]
                            for ch in rec["channels"]))
        result = validate_ims_report(data)
        self.assertEqual(result["counts_by_issue"]["bearing_mapping_unverified"], 8)

    def test_injected_failure_truth_is_rejected(self):
        data = report()
        for value in ("bearing_fault", 0, False):
            with self.subTest(value=value):
                sample = copy.deepcopy(data)
                sample["ground_truth"]["window_fault_label"] = value
                with self.assertRaisesRegex(ValueError, "must not invent"):
                    validate_ims_report(sample)

    def test_review_flags_do_not_change_raw_feature_values(self):
        data = report()
        before = json.dumps(data, sort_keys=True)
        validate_ims_report(data, expected_interval_s=10, verify_files=True)
        self.assertEqual(json.dumps(data, sort_keys=True), before)

    def test_crest_threshold_is_configurable_not_diagnosis(self):
        baseline = validate_ims_report(report())
        altered = validate_ims_report(report(), crest_review_threshold=1.0)
        self.assertGreaterEqual(altered["counts_by_issue"]["high_crest_review"],
                                baseline["counts_by_issue"].get("high_crest_review", 0))
        for invalid in (0, float("nan"), "6"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_ims_report(report(), crest_review_threshold=invalid)


class TrainOnlyPreprocessingTests(unittest.TestCase):
    def test_fit_uses_train_only_and_disjoint_heldout_runs(self):
        train = report("1", unit="g")
        heldout = report("2", unit="g")
        scaler = fit_train_scaler([train], [heldout])
        self.assertEqual(scaler["fit_on"], "training_runs_only")
        self.assertEqual(scaler["train_run_ids"], ["ims-set-1"])
        self.assertEqual(scaler["heldout_run_ids"], ["ims-set-2"])
        self.assertEqual(tuple(scaler["features"]), FEATURE_KEYS)
        train_rms = [ch["rms_native"] for rec in train["records"] for ch in rec["channels"]]
        self.assertAlmostEqual(scaler["parameters"]["rms_native"]["mean"],
                               sum(train_rms) / len(train_rms))
        # Altering evaluation measurements must NOT affect the fitted stats.
        modified = copy.deepcopy(heldout)
        for rec in modified["records"]:
            for channel in rec["channels"]:
                channel["rms_native"] = 1000.0
                channel["peak_to_peak_native"] = 2000.0
                channel["crest_factor"] = 2.0
        self.assertEqual(fit_train_scaler([train], [modified]), scaler)
        transformed = transform_report(heldout, scaler, partition="heldout")
        self.assertEqual(len(transformed), 8)
        self.assertTrue(all(row["run_id"] == "ims-set-2" for row in transformed))
        self.assertTrue(all(row["partition"] == "heldout" for row in transformed))
        self.assertAlmostEqual(transformed[0]["rms_native_z"],
                               (heldout["records"][0]["channels"][0]["rms_native"] -
                                scaler["parameters"]["rms_native"]["mean"]) /
                               scaler["parameters"]["rms_native"]["std"])

    def test_leakage_guards_run_overlap_empty_partition(self):
        a = report("1", unit="g")
        b = report("2", unit="g")
        for train, heldout in (([a],[a]), ([a,a],[b]), ([],[b]), ([a],[])):
            with self.subTest(train=len(train), heldout=len(heldout)), self.assertRaises(ValueError):
                fit_train_scaler(train, heldout)
        scaler = fit_train_scaler([a], [b])
        with self.assertRaises(ValueError):
            transform_report(a, scaler, partition="heldout")
        with self.assertRaises(ValueError):
            transform_report(b, scaler, partition="train")

    def test_mixed_physical_units_and_rates_refused(self):
        a = report("1", unit="g")
        for b in (report("2",unit="V"), report("2",unit="g",rate=16)):
            with self.assertRaisesRegex(ValueError, "different units, sample rates"):
                fit_train_scaler([a], [b])
        with self.assertRaisesRegex(ValueError, "unit must be verified"):
            fit_train_scaler([report("1")], [report("2")])

    def test_constant_feature_handled_without_division_by_zero(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "2004.02.12.10.32.39").write_text("0 0 0 0\n"*4,encoding="ascii")
            a = inspect_ims_directory(folder, test_set="1", sample_rate_hz=8,
                                      expected_samples=4, expected_channels=4, value_unit="g")
            b = inspect_ims_directory(folder, test_set="2", sample_rate_hz=8,
                                      expected_samples=4, expected_channels=4, value_unit="g")
            scaler = fit_train_scaler([a],[b])
            self.assertTrue(all(scaler["parameters"][name]["constant"] for name in FEATURE_KEYS))
            outputs = transform_report(b, scaler, partition="heldout")
            self.assertTrue(all(all(record[key+"_z"] == 0 for key in FEATURE_KEYS)
                                for record in outputs))

    def test_scaler_provenance_and_partition_validation(self):
        a, b = report("1", unit="g"), report("2",unit="g")
        scaler = fit_train_scaler([a],[b])
        other = report("2",unit="V")
        with self.assertRaisesRegex(ValueError, "incompatible scaler provenance"):
            transform_report(other, scaler, partition="heldout")
        with self.assertRaises(ValueError):
            transform_report(b, scaler, partition="unknown")


class ValidationCLI(unittest.TestCase):
    def test_offline_cli_checks_hashes_and_rejects_overwrite(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "inspection.json"
            write_local_manifest(path, report())
            outfile = folder / "quality.json"
            args = [sys.executable, "-m", "motorpulse.ims_validation",
                    "--report", str(path), "--verify-files", "--expected-interval-s", "20",
                    "--out", str(outfile)]
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            result = subprocess.run(args, cwd=folder, env=env, capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode,0,result.stderr)
            quality = json.loads(outfile.read_text(encoding="utf-8"))
            self.assertTrue(quality["verified_file_checksums"])
            self.assertEqual(quality["counts_by_issue"]["cadence_deviation"],1)
            result = subprocess.run(args, cwd=folder, env=env, capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode,2)
            self.assertIn("error:",result.stderr)

    def test_cli_rejects_invalid_interval_without_output(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            input_path = folder / "inspection.json"
            write_local_manifest(input_path, report())
            output = folder / "out.json"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            p = subprocess.run([sys.executable, "-m", "motorpulse.ims_validation",
                                "--report", str(input_path), "--expected-interval-s", "0",
                                "--out", str(output)], cwd=folder, env=env,
                               capture_output=True,text=True,timeout=25)
            self.assertEqual(p.returncode,2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
