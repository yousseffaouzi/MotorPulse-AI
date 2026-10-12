"""MP-037: frozen, source-verified explanatory rule/model comparisons."""
from __future__ import annotations

from copy import deepcopy
import json
from math import isclose, sqrt
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from motorpulse.anomaly import FEATURES, _vector
from motorpulse.comparison import (
    COMPARISON_VERSION, OUTCOMES, _outcome, compare_experiment,
    explain_window, markdown, save_report,
)
from motorpulse.experiment import run_experiment
from motorpulse.scenarios import AssetScenario
from motorpulse.sim import MotorSimulator, classify
from motorpulse.splits import _hash

ROOT = Path(__file__).resolve().parents[1]


def experiment_config():
    return {
        "experiment_version": "1.0.0",
        "seeds": [11, 22, 33],
        "ticks": 8,
        "assets": {"assets": [
            {"asset_id": "MTR-A1", "name": "Healthy", "scenario": "healthy"},
            {"asset_id": "MTR-A2", "name": "Future bearing fault",
             "scenario": "bearing_wear", "severity": 0.8, "onset_tick": 4},
            {"asset_id": "MTR-A3", "name": "Noisy with missing/outlier",
             "scenario": "healthy", "speed_variation_pct": .2,
             "sensor_missing_onset_tick": 2, "sensor_missing_duration_ticks": 1,
             "sensor_outlier_onset_tick": 4, "sensor_outlier_duration_ticks": 1,
             "sensor_outlier_g": 1.},
        ]},
        "virtual_start_utc": "2026-01-01T00:00:00+00:00",
        "step_seconds": 1.5, "split_seed": 42, "split_ratios": [.6, .2, .2],
    }


def event_of(asset: AssetScenario, tick: int = 1):
    sim = MotorSimulator(seed=10, assets=(asset,))
    data = None
    for _ in range(tick):
        data = sim.step()["assets"][0]
    return {**data, "tick": tick, "export_id": "synthetic-fixture"}


def fake_model(event, threshold=0.1, centers=None):
    if centers is None:
        centers = list(_vector(event))
    return {
        "center": centers, "effective_scales": [1.] * len(FEATURES),
        "calibration": {"threshold": threshold},
    }


class WindowExplanationTests(unittest.TestCase):
    def test_feature_contributions_reconstruct_score_squared(self):
        event = event_of(AssetScenario("MTR-A1", "Good motor"))
        values = _vector(event)
        model = fake_model(event, centers=[v - i for i,v in enumerate(values, start=1)])
        explanation = explain_window(event, model, group_id="group-A")
        score = explanation["model"]["score"]
        terms = explanation["model"]["contributions"]
        self.assertAlmostEqual(score, sqrt(11))
        self.assertEqual([c["feature"] for c in terms], list(FEATURES))
        self.assertAlmostEqual(sum(t["squared_distance_contribution"] for t in terms), score**2)
        self.assertAlmostEqual(sum(t["fraction_of_score_squared"] for t in terms), 1)
        self.assertEqual(explanation["outcome"], "model_only_false_positive")
        self.assertFalse(explanation["synthetic_fault_positive"])

    def test_zero_score_and_strict_threshold_tie_not_alert(self):
        event = event_of(AssetScenario("MTR-A1", "Good motor"))
        model = fake_model(event, threshold=0.)
        explained = explain_window(event, model, group_id="run-a")
        self.assertEqual(explained["model"]["score"], 0)
        self.assertEqual(explained["model"]["decision"], "within_threshold")
        self.assertTrue(all(t["fraction_of_score_squared"] == 0 for t in
                            explained["model"]["contributions"]))
        self.assertEqual(explained["outcome"], "shared_true_negative")

    def test_rule_only_and_shared_false_positives(self):
        event = event_of(AssetScenario("MTR-A1", "Good motor"))
        event["rms_g"] = 0.4  # intentionally fabricated unit-level event
        event["health"], event["reasons"] = classify(
            event["rms_g"], event["temperature_c"], event["crest_factor"])
        model = fake_model(event, threshold=.1)
        rule_only = explain_window(event, model, group_id="run-a")
        self.assertEqual(rule_only["outcome"], "rules_only_false_positive")
        self.assertIn("elevated_rms", rule_only["rules"]["triggered_checks"])
        self.assertIn("elevated vibration RMS", rule_only["rules"]["reasons"])
        other = fake_model(event, threshold=.1,
                           centers=[v-1 for v in _vector(event)])
        shared = explain_window(event, other, group_id="run-a")
        self.assertEqual(shared["outcome"], "shared_false_positive")

    def test_scheduled_fault_not_positive_before_onset(self):
        event = event_of(AssetScenario("MTR-A1", "Bearing", scenario="bearing_wear",
                                       severity=.8, onset_tick=4))
        out = explain_window(event, fake_model(event), group_id="run")
        self.assertEqual(out["effective_synthetic_truth"], "healthy")
        self.assertEqual(out["configured_future_or_active_fault"], "bearing_wear")
        self.assertFalse(out["synthetic_fault_positive"])
        self.assertEqual(out["fault_phase"], "scheduled")

    def test_missing_and_outlier_are_abstentions_without_score(self):
        for name, scenario in [
            ("missing", AssetScenario("MTR-A1", "Missing sensor",
                                      sensor_missing_onset_tick=1,
                                      sensor_missing_duration_ticks=1)),
            ("outlier", AssetScenario("MTR-A1", "Outlier sensor",
                                      sensor_outlier_onset_tick=1,
                                      sensor_outlier_duration_ticks=1,
                                      sensor_outlier_g=.8)),
        ]:
            event = event_of(scenario)
            with self.subTest(quality=name):
                out = explain_window(event, {"calibration":{"threshold": 2.}}, group_id="run")
                self.assertEqual(out["outcome"], "sensor_abstention")
                self.assertIsNone(out["model"]["score"])
                self.assertEqual(out["model"]["contributions"], [])
                self.assertEqual(out["rules"]["decision"], "abstain")

    def test_rule_recomputation_rejects_tampered_source_reason_or_health(self):
        event = event_of(AssetScenario("MTR-A1", "Good motor"))
        for change in ({"health":"critical"}, {"reasons":["fabricated"]},
                       {"reasons":"normal"}, {"sensor_quality":"missing"}):
            tampered = {**event, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                explain_window(tampered, fake_model(event), group_id="run")

    def test_invalid_quality_and_configured_truth_rejected(self):
        event = event_of(AssetScenario("MTR-A1", "Good motor"))
        for change in ({"sensor_quality":"broken"}, {"configured_scenario":"unknown"},
                       {"scenario":"unknown"}, {"sample_count": 32}):
            tampered = {**event, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                explain_window(tampered, fake_model(event), group_id="run")

    def test_outcome_truth_table(self):
        self.assertEqual(_outcome(True, True, False, False), "shared_false_negative")
        self.assertEqual(_outcome(True, True, True, False), "model_only_true_positive")
        self.assertEqual(_outcome(True, True, False, True), "rules_only_true_positive")
        self.assertEqual(_outcome(True, True, True, True), "shared_true_positive")
        self.assertEqual(_outcome(False, True, False, False), "shared_true_negative")
        self.assertEqual(_outcome(True, False, True, True), "sensor_abstention")


class ComparisonIntegrationTests(unittest.TestCase):
    def test_same_cohort_reproducible_metric_equality_and_bounded_examples(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/"exp"
            run_experiment(experiment_config(), root)
            report = compare_experiment(root, partition="test", max_examples=3)
            second = compare_experiment(root, partition="test", max_examples=3)
            self.assertEqual(report, second)
            self.assertEqual(report["comparison_version"], COMPARISON_VERSION)
            self.assertEqual(report["comparison_sha256"],
                             _hash({k:v for k,v in report.items() if k!="comparison_sha256"}))
            baseline = json.loads((root/"test-metrics.json").read_text())
            self.assertEqual(report["overall"], baseline["overall"])
            self.assertEqual(report["baseline_evaluation_sha256"], baseline["evaluation_sha256"])
            self.assertEqual(report["comparison_cohort"]["abstentions"],
                             baseline["comparison_cohort"]["abstentions"])
            self.assertEqual(sum(report["outcome_counts"].values()),
                             report["comparison_cohort"]["total_windows"])
            self.assertEqual(set(report["examples"]), set(OUTCOMES))
            self.assertTrue(all(len(samples) <= 3 for samples in report["examples"].values()))
            self.assertIn("False positives", markdown(report))
            self.assertEqual(sum(report["agreement"].values()),
                             report["comparison_cohort"]["total_windows"])
            for group in report["examples"].values():
                for example in group:
                    self.assertIn("configured_future_or_active_fault", example)
                    self.assertIn("effective_synthetic_truth", example)
            self.assertFalse(report["source"] != "synthetic_only")

    def test_zero_examples_validation_no_mutation_and_distinct_partition(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/"exp"
            run_experiment(experiment_config(),root)
            initial=(root/"model-artifact.json").read_bytes()
            report=compare_experiment(root,partition="validation",max_examples=0)
            self.assertTrue(all(not values for values in report["examples"].values()))
            self.assertEqual(initial,(root/"model-artifact.json").read_bytes())
            for value in (-1,13,True,1.5):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    compare_experiment(root,max_examples=value)
            with self.assertRaises(ValueError):
                compare_experiment(root,partition="train")

    def test_experiment_provenance_corruption_fails_closed(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/"exp"
            run_experiment(experiment_config(),root)
            index=root/"experiment-index.json"
            contents=index.read_bytes()
            altered=json.loads(contents)
            altered["model_sha256"]="f"*64
            index.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError,"index checksum"):
                compare_experiment(root)
            index.write_bytes(contents)
            artifact=root/"model-artifact.json"
            artifact.write_text(artifact.read_text()+" ")
            with self.assertRaises(ValueError):
                compare_experiment(root)

    def test_reports_are_exclusive_and_checksum_verified(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            run_experiment(experiment_config(),root/"exp")
            report=compare_experiment(root/"exp",max_examples=2)
            save_report(report,root/"compare.json",root/"compare.md")
            self.assertEqual(json.loads((root/"compare.json").read_text()),report)
            self.assertIn("Standardized", (root/"compare.md").read_text().title())
            with self.assertRaises(ValueError):
                save_report(report,root/"compare.json",root/"other.md")
            self.assertFalse((root/"other.md").exists())
            changed=deepcopy(report)
            changed["overall"]["model"]["fp"] += 1
            with self.assertRaisesRegex(ValueError,"checksum"):
                save_report(changed,root/"bad.json",root/"bad.md")
            self.assertFalse((root/"bad.json").exists())

    def test_cli_json_markdown_write_once(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            run_experiment(experiment_config(),root/"exp")
            command=[sys.executable,"-m","motorpulse.comparison",
                     "--experiment-dir",str(root/"exp"),
                     "--max-examples","1","--out-json",str(root/"cli.json"),
                     "--out-md",str(root/"cli.md")]
            run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads((root/"cli.json").read_text())["example_selection"]["max_per_outcome"],1)
            again=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0)
            self.assertIn("new", again.stderr.lower())


if __name__ == "__main__":
    unittest.main()
