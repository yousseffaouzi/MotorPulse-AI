"""MP-036: offline synthetic-only frozen-model stress slicing regression checks."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.experiment import run_experiment
from motorpulse.robustness import (
    from_experiment, markdown, save_report, stress_labels, summarize_stress_rows,
)
from motorpulse.splits import _hash


def scenario():
    return {
        "experiment_version": "1.0.0", "seeds": [11, 22, 33], "ticks": 8,
        "assets": {"assets": [
            {"asset_id": "MTR-01", "name": "Normal", "scenario": "healthy"},
            {"asset_id": "MTR-02", "name": "Speed and load", "scenario": "healthy",
             "speed_variation_pct": .2, "load_variation_pct": .3,
             "sensor_noise_g": .1, "sensor_drift_g_per_tick": .001,
             "sensor_missing_onset_tick": 2, "sensor_missing_duration_ticks": 2},
            {"asset_id": "MTR-03", "name": "Bearing", "scenario": "bearing_wear",
             "severity": .8, "onset_tick": 3, "progression": "linear",
             "ramp_ticks": 3, "sensor_outlier_onset_tick": 4,
             "sensor_outlier_duration_ticks": 2, "sensor_outlier_g": 1},
        ]},
        "virtual_start_utc": "2026-01-01T00:00:00+00:00", "step_seconds": 1.5,
        "split_seed": 42, "split_ratios": [.6, .2, .2],
    }


class StressLabelsTest(unittest.TestCase):
    def event(self):
        return {
            "operating_config": {"speed_variation_pct": 0.2, "load_variation_pct": 0.3,
                                 "sensor_noise_g": .1, "sensor_drift_g_per_tick": -.001},
            "scenario": "healthy", "fault_phase": "scheduled", "severity": 0.,
            "configured_scenario": "bearing_wear", "configured_severity": .8,
            "progression": "linear", "sensor_quality": "good", "onset_tick": 4,
            "tick": 1,
        }

    def test_settings_and_effective_truth_separated(self):
        result = stress_labels(self.event())
        self.assertEqual(result["effective_fault"], "healthy")
        self.assertEqual(result["configured_fault"], "bearing_wear")
        self.assertEqual(result["sensor_drift"], "negative_high")
        self.assertEqual(result["effective_strength"], "healthy")
        self.assertEqual(result["configured_strength"], "high")

    def test_finite_ranges_and_metadata_strict(self):
        for bad in [True, -1, float("nan"), float("inf"), .21, "0.2"]:
            row = self.event()
            row["operating_config"]["speed_variation_pct"] = bad
            with self.subTest(value=bad), self.assertRaises(ValueError):
                stress_labels(row)
        for change in ({"scenario": "bearing_wear"}, {"fault_phase": "invalid"},
                       {"severity": .6}, {"configured_severity": 1.5},
                       {"configured_scenario": "unknown"}):
            row = self.event()
            row.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                stress_labels(row)


class StressSummaryTest(unittest.TestCase):
    def row(self, tick, *, eligible=True, positive=False, model=False, rule=False):
        return {
            "group_id": "run-1", "asset_id": "MTR-01", "tick": tick,
            "step_seconds": 2., "timestamp_utc": "2026-01-01T00:00:00+00:00",
            "positive": positive, "scenario": "imbalance" if positive else "healthy",
            "eligible": eligible, "quality": "good" if eligible else "missing",
            "anomaly_alert": model, "rule_alert": rule,
            "score": float(tick) if eligible else None,
            "stress": {**{name: "same" for name in (
                "speed_variation", "load_variation", "vibration_noise", "sensor_drift",
                "joint_operating_regime", "configured_fault", "configured_strength",
                "progression", "onset_timing")},
                "effective_fault": "imbalance" if positive else "healthy",
                "effective_strength": "high" if positive else "healthy",
                "fault_phase": "steady" if positive else "healthy",
                "sensor_quality": "good" if eligible else "missing"},
        }

    def test_abstentions_and_undefined_metrics(self):
        rows = [self.row(1,eligible=False), self.row(2,positive=True,model=True),
                self.row(3,positive=True,rule=True)]
        out = summarize_stress_rows(rows)
        self.assertEqual(out["coverage"]["abstentions"], {"missing": 1})
        self.assertEqual(out["overall"]["model"]["tp"], 1)
        self.assertIsNone(out["overall"]["model"]["false_positive_rate"])
        self.assertIsNone(out["overall"]["model"]["average_precision"])
        self.assertEqual(out["by_stress"]["speed_variation"]["same"]["model"]["n"], 2)
        self.assertIsNone(out["by_stress"]["sensor_quality"]["missing"]["detection_episodes"])

    def test_false_positive_exposure_and_track_delay(self):
        rows = [self.row(1,model=True), self.row(2,positive=True),
                self.row(3,positive=True,model=True)]
        out = summarize_stress_rows(rows)
        self.assertEqual(out["overall"]["model"]["fp"], 1)
        self.assertEqual(out["overall"]["model"]["false_alarms_per_simulated_negative_hour"], 1800)
        self.assertEqual(out["detection_episodes"]["mean_delay_seconds"], 2)

    def test_disordered_or_partial_tracks_rejected(self):
        for rows in ([self.row(2)], [self.row(1), self.row(3)]):
            with self.assertRaises(ValueError):
                summarize_stress_rows(rows)


class RobustnessIntegrationTest(unittest.TestCase):
    def test_reproducible_artifact_verified_and_same_cohort(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_experiment(scenario(), root / "a")
            report = from_experiment(root / "a", partition="test")
            again = from_experiment(root / "a", partition="test")
            self.assertEqual(report, again)
            self.assertEqual(report["robustness_sha256"],
                             _hash({k:v for k,v in report.items() if k != "robustness_sha256"}))
            baseline = json.loads((root/"a"/"test-metrics.json").read_text())
            self.assertEqual(report["overall"], baseline["overall"])
            self.assertEqual(report["baseline_evaluation_sha256"], baseline["evaluation_sha256"])
            self.assertIn("vibration_noise", report["by_stress"])
            self.assertIn("speed_variation", report["by_stress"])
            self.assertIn("sensor_quality", report["by_stress"])
            self.assertEqual(report["fixed_training_threshold"], baseline["threshold_fixed_from_training"])
            self.assertIn("synthetic", markdown(report).lower())
            jsonfile, mdfile = root/"robust.json", root/"robust.md"
            save_report(report, jsonfile, mdfile)
            with self.assertRaises(ValueError):
                save_report(report, jsonfile, mdfile)
            self.assertEqual(json.loads(jsonfile.read_text()), report)

    def test_corrupted_index_split_and_source_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/"experiment"
            run_experiment(scenario(), root)
            idx = root/"experiment-index.json"
            before = idx.read_bytes()
            raw = json.loads(before)
            raw["model_sha256"] = "a"*64
            idx.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError, "index checksum"):
                from_experiment(root)
            idx.write_bytes(before)
            split = root/"split-plan.json"
            split.write_text(split.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "artifact bytes"):
                from_experiment(root)

    def test_no_training_partition_and_no_overwrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/"experiment"
            run_experiment(scenario(), root)
            with self.assertRaisesRegex(ValueError,"validation or test"):
                from_experiment(root,partition="train")
            report = from_experiment(root)
            kept = Path(directory)/"kept.md"
            kept.write_text("user")
            jsonfile = Path(directory)/"brand-new.json"
            with self.assertRaises(ValueError):
                save_report(report,jsonfile,kept)
            self.assertFalse(jsonfile.exists())
            self.assertEqual(kept.read_text(),"user")


if __name__ == "__main__":
    unittest.main()
