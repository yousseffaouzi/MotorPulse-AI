"""MP-038: validation-only cutoff selection and frozen synthetic test auditing."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from motorpulse.calibration import (
    CALIBRATION_VERSION, _at_threshold, _curve, _target,
    calibrate_experiment, choose_threshold, markdown, save_report,
)
from motorpulse.experiment import run_experiment
from motorpulse.splits import _hash

ROOT = Path(__file__).resolve().parents[1]


def config():
    return {
        "experiment_version": "1.0.0", "seeds": [11, 22, 33], "ticks": 8,
        "assets": {"assets": [
            {"asset_id": "MTR-A1", "name": "Healthy", "scenario": "healthy"},
            {"asset_id": "MTR-A2", "name": "Late bearing fault", "scenario": "bearing_wear",
             "severity": .8, "onset_tick": 4},
            {"asset_id": "MTR-A3", "name": "Sensor issues", "scenario": "healthy",
             "speed_variation_pct": .2, "sensor_missing_onset_tick": 2,
             "sensor_missing_duration_ticks": 1, "sensor_outlier_onset_tick": 4,
             "sensor_outlier_duration_ticks": 1, "sensor_outlier_g": .8},
        ]},
        "virtual_start_utc": "2026-01-01T00:00:00+00:00",
        "step_seconds": 1.5, "split_seed": 42,
        "split_ratios": [.6, .2, .2],
    }


def rows(negatives, positives=()):
    return [{"score": float(x), "positive": False} for x in negatives] + [
        {"score": float(x), "positive": True} for x in positives
    ]


class ThresholdSelectionTests(unittest.TestCase):
    def test_zero_budget_never_exceeds_negative_score(self):
        result = choose_threshold(rows([.5,1,3], [2,4]), target_fpr=0)
        self.assertEqual(result["threshold"],3)
        self.assertEqual(result["allowed_validation_false_positives"],0)
        self.assertEqual(result["achieved_validation_false_positives"],0)

    def test_one_third_budget_tie_group_not_split(self):
        result = choose_threshold(rows([1, 2, 2], [3, 4]), target_fpr=1/3)
        self.assertEqual(result["threshold"],2)
        self.assertEqual(result["allowed_validation_false_positives"],1)
        self.assertEqual(result["achieved_validation_false_positives"],0)

    def test_lowest_nonnegative_threshold_with_empirical_budget(self):
        case = rows([1,2,3,4], [.25,2.5,5])
        choice = choose_threshold(case,target_fpr=.25)
        self.assertEqual(choice["threshold"],3)
        self.assertEqual(choice["achieved_validation_false_positives"],1)
        self.assertEqual(choice["achieved_validation_false_positive_rate"],.25)
        self.assertEqual(choose_threshold(case,target_fpr=1)["threshold"],0)

    def test_no_positive_validation_windows_is_explicit(self):
        choice=choose_threshold(rows([1,2,3]),target_fpr=0)
        self.assertEqual(choice["validation_eligible_positive_windows"],0)
        self.assertEqual(choice["threshold"],3)

    def test_absent_negative_validation_windows_rejected(self):
        for sample in ([],rows([], [1,2,3])):
            with self.assertRaisesRegex(ValueError,"negative windows"):
                choose_threshold(sample,target_fpr=.05)

    def test_bad_budgets_and_nonfinite_scores_rejected(self):
        for bad in (-.01,1.01,float("nan"),float("inf"), True, None, "0.05"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                choose_threshold(rows([1]),target_fpr=bad)
        for bad in (-1, True, float("nan"),float("inf"),"1",None):
            with self.subTest(score=bad),self.assertRaises(ValueError):
                choose_threshold([{"score":bad,"positive":False}],target_fpr=.2)
        with self.assertRaises(ValueError):
            choose_threshold([{"score":1,"positive":1}],target_fpr=.5)

    def test_heldout_test_rows_cannot_influence_selection(self):
        validation=rows([1,2,3,3,4], [1,5,6])
        first=choose_threshold(validation,target_fpr=.2)
        other_test_cohort=rows([90,500],[.001])
        # Selection has no test input at all, unlike a dataset-wide quantile.
        self.assertEqual(first,choose_threshold(validation,target_fpr=.2))
        self.assertEqual(first["threshold"],4)
        self.assertNotEqual(first["threshold"], max(r["score"] for r in other_test_cohort))

    def test_selected_score_strict_comparison_and_abstention(self):
        example=[
            {"eligible":True,"positive":False,"score":2,"rule_alert":False},
            {"eligible":True,"positive":True,"score":2,"rule_alert":True},
            {"eligible":True,"positive":True,"score":3,"rule_alert":False},
            {"eligible":False,"positive":True,"score":None,"rule_alert":False},
        ]
        result=_at_threshold(example,2)
        self.assertEqual([r["anomaly_alert"] for r in result],[False,False,True])
        self.assertEqual(len(result),3)

    def test_curve_bounded_and_contains_selected_and_original(self):
        example=[
            {"score":float(i+1),"eligible":True,"positive":i%3 == 0,
             "step_seconds":1., "rule_alert":False}
            for i in range(200)
        ]
        curve=_curve(example, 2., 50.)
        self.assertLessEqual(len(curve),35)
        self.assertTrue(any(p["is_original_training_cutoff"] for p in curve))
        self.assertTrue(any(p["is_selected_validation_cutoff"] for p in curve))
        self.assertEqual([p["threshold"] for p in curve],
                         sorted(p["threshold"] for p in curve))


class CalibrationIntegrationTests(unittest.TestCase):
    def test_full_validation_selection_and_original_test_evaluation(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/"run"
            run_experiment(config(),root)
            before=(root/"model-artifact.json").read_bytes()
            result=calibrate_experiment(root,target_fpr=.05)
            again=calibrate_experiment(root,target_fpr=.05)
            self.assertEqual(result,again)
            self.assertEqual(result["threshold_calibration_version"],CALIBRATION_VERSION)
            self.assertEqual(result["threshold_calibration_sha256"],
                _hash({k:v for k,v in result.items() if k!="threshold_calibration_sha256"}))
            self.assertEqual(before,(root/"model-artifact.json").read_bytes())
            for name in ("validation","test_after_selection"):
                source="validation" if name=="validation" else "test"
                baseline=json.loads((root/(source+"-metrics.json")).read_text())
                self.assertEqual(result[name]["original_training_threshold"],baseline["overall"])
                self.assertEqual(result[name]["comparison_cohort"],baseline["comparison_cohort"])
                self.assertEqual(result[name]["selected_threshold"]["rules"],baseline["overall"]["rules"])
            self.assertTrue(result["no_test_labels_used_for_selection"])
            self.assertTrue(result["original_model_unchanged"])
            self.assertLessEqual(
                result["validation"]["selected_threshold"]["model"]["false_positive_rate"],.05)
            self.assertIn("only validation",markdown(result).lower())

    def test_provenance_corruption_refused(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/"run"
            run_experiment(config(),root)
            index=root/"experiment-index.json"
            original=index.read_bytes()
            doc=json.loads(original);doc["model_sha256"]="f"*64
            index.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"checksum"):
                calibrate_experiment(root)
            index.write_bytes(original)
            original_model=root/"model-artifact.json"
            original_model.write_text(original_model.read_text()+" ")
            with self.assertRaises(ValueError):
                calibrate_experiment(root)

    def test_no_overwrite_checksum_and_rollback(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            run_experiment(config(),root/"run")
            result=calibrate_experiment(root/"run")
            jsonfile=root/"calibration.json"
            mdfile=root/"calibration.md"
            save_report(result,jsonfile,mdfile)
            self.assertEqual(json.loads(jsonfile.read_text()),result)
            self.assertIn("validation",mdfile.read_text().lower())
            with self.assertRaises(ValueError):
                save_report(result,jsonfile,root/"new.md")
            self.assertFalse((root/"new.md").exists())
            edited=deepcopy(result)
            edited["selection"]["threshold"]+=1
            with self.assertRaisesRegex(ValueError,"checksum"):
                save_report(edited,root/"tampered.json",root/"tampered.md")
            self.assertFalse((root/"tampered.json").exists())

    def test_cli_write_once(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            run_experiment(config(),root/"run")
            command=[
                sys.executable,"-m","motorpulse.calibration",
                "--experiment-dir",str(root/"run"),"--target-fpr","0.05",
                "--out-json",str(root/"threshold.json"),
                "--out-md",str(root/"threshold.md"),
            ]
            first=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(json.loads((root/"threshold.json").read_text())["selection"]["target_false_positive_rate"],.05)
            second=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            self.assertIn("unused",second.stderr.lower())


if __name__ == "__main__":
    unittest.main()
