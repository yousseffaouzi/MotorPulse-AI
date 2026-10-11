"""MP-026: guardrails tying published model assumptions to executable fixtures."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from motorpulse.scenarios import AssetScenario, parse_configuration
from motorpulse.schema import SAMPLE_COUNT, SAMPLE_RATE_HZ, SENSOR_UNITS, validate_snapshot
from motorpulse.signals import BEARING_IMPACT_ORDER, HARMONIC_AMPLITUDES_G, NOISE_STD_G
from motorpulse.sim import DEFAULT_START_TIME_UTC, MotorSimulator, classify, features
from motorpulse.spectral import BAND_LOW_HZ, BAND_HIGH_HZ, ROLLING_WINDOW_TICKS

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs/MODEL_ASSUMPTIONS.md"


class ModelReferenceTests(unittest.TestCase):
    def test_reference_exists_and_explicitly_limits_claims(self):
        contents = REFERENCE.read_text(encoding="utf-8")
        for expected in (
            "1024", "0.085", "4.8", "Hann", "unavailable", "suspect",
            "RUL", "uncertainty", "not a physical motor digital twin",
            "not globally unique", "NASA", "g peak",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected.lower(), contents.lower())

    def test_documented_model_constants(self):
        self.assertEqual((SAMPLE_RATE_HZ, SAMPLE_COUNT), (1024, 1024))
        self.assertEqual(SAMPLE_COUNT / SAMPLE_RATE_HZ, 1.0)
        self.assertEqual((BAND_LOW_HZ, BAND_HIGH_HZ), (80.0, 400.0))
        self.assertEqual(ROLLING_WINDOW_TICKS, 5)
        self.assertEqual(NOISE_STD_G, 0.014)
        self.assertEqual(BEARING_IMPACT_ORDER, 4.8)
        self.assertEqual(HARMONIC_AMPLITUDES_G["healthy"], (0.12, 0.015))
        self.assertEqual(HARMONIC_AMPLITUDES_G["imbalance"], (0.62, 0.020))
        self.assertEqual(HARMONIC_AMPLITUDES_G["bearing_wear"], (0.22, 0.025))
        self.assertEqual(HARMONIC_AMPLITUDES_G["misalignment"], (0.14, 0.28))
        self.assertEqual(HARMONIC_AMPLITUDES_G["overload"], (0.20, 0.025))
        self.assertEqual(SENSOR_UNITS["vibration_acceleration"], "g")

    def test_timestamp_and_sensor_units_match_reference(self):
        self.assertEqual(DEFAULT_START_TIME_UTC,
                         datetime(2026, 1, 1, tzinfo=timezone.utc))
        sim = MotorSimulator(seed=42)
        a, b = sim.step(), sim.step()
        for sample in (a, b):
            validate_snapshot(sample)
            for event in sample["assets"]:
                self.assertEqual(event["sample_count"], SAMPLE_COUNT)
                self.assertEqual(event["sample_rate_hz"], SAMPLE_RATE_HZ)
                self.assertEqual(event["units"], SENSOR_UNITS)
                self.assertEqual(event["window_duration_s"], 1.0)
        self.assertEqual(a["recorded_at_utc"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(b["recorded_at_utc"], "2026-01-01T00:00:01.500000+00:00")

    def test_threshold_boundaries_are_only_demo_rules(self):
        self.assertEqual(classify(0.12, 47.0, 1.4)[0], "normal")
        self.assertEqual(classify(0.36, 47.0, 1.4)[0], "warning")
        self.assertEqual(classify(0.55, 47.0, 1.4)[0], "critical")
        self.assertEqual(classify(0.12, 82.0, 1.4)[0], "warning")
        self.assertEqual(classify(0.12, 92.0, 1.4)[0], "critical")
        self.assertEqual(classify(0.20, 40.0, 2.7)[0], "warning")
        self.assertEqual(features([0.0] * 16)["crest_factor"], 0.0)

    def test_injected_sensor_issue_is_not_machine_fault_label(self):
        asset = AssetScenario(
            "MTR-20", "Fault plus dropout", scenario="imbalance", severity=0.6,
            sensor_missing_onset_tick=1, sensor_missing_duration_ticks=1,
            sensor_outlier_onset_tick=2, sensor_outlier_duration_ticks=1,
            sensor_outlier_g=1.0,
        )
        sim = MotorSimulator(seed=19, assets=(asset,))
        missing, outlier, recovered = (sim.step()["assets"][0] for _ in range(3))
        self.assertEqual(missing["scenario"], "imbalance")
        self.assertEqual(missing["sensor_quality"], "missing")
        self.assertEqual(missing["health"], "unavailable")
        self.assertIsNone(missing["rms_g"])
        self.assertIsNone(missing["rolling_rms_mean_g"])
        self.assertEqual(outlier["scenario"], "imbalance")
        self.assertEqual(outlier["sensor_quality"], "outlier")
        self.assertEqual(outlier["health"], "suspect")
        self.assertEqual(recovered["sensor_quality"], "good")

    def test_old_telemetry_and_scenarios_still_validate(self):
        with (ROOT / "docs/examples/snapshot-v1.json").open(encoding="utf-8") as fp:
            validate_snapshot(json.load(fp))
        for path in (
            "docs/examples/scenarios-v1.json",
            "docs/examples/scenarios-progressive.json",
            "docs/examples/operations-v1.json",
        ):
            with self.subTest(path=path), (ROOT / path).open(encoding="utf-8") as fp:
                config = json.load(fp)
                assets = parse_configuration(config)
                self.assertGreaterEqual(len(assets), 1)

    def test_document_links_to_existing_local_guides(self):
        for path in (
            "ARCHITECTURE.md", "TELEMETRY.md", "SIGNALS.md", "SPECTRAL.md",
            "SCENARIOS.md", "PROGRESSION.md", "OPERATIONS.md",
            "SIMULATION_CONTROL.md", "CONFIG_FILE.md",
        ):
            with self.subTest(path=path):
                self.assertTrue((ROOT / "docs" / path).is_file())
                self.assertIn(path, REFERENCE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
