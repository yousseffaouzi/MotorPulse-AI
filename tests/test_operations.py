"""MP-025: operating variability, sensor-quality flags and deterministic recovery."""
import copy
import json
import math
import unittest

from motorpulse.controller import SimulationController
from motorpulse.scenarios import AssetScenario, parse_configuration
from motorpulse.schema import validate_snapshot
from motorpulse.sim import MotorSimulator


def config(**overrides):
    data = dict(asset_id="MTR-20", name="Test motor", scenario="healthy")
    data.update(overrides)
    return AssetScenario(**data)


class OperatingVariabilityTests(unittest.TestCase):
    def test_default_sensor_is_good_and_original_rules_hold(self):
        data = MotorSimulator().step()
        for row in data["assets"]:
            self.assertEqual(row["sensor_quality"], "good")
            self.assertEqual(row["sensor_quality_reasons"], [])
            self.assertEqual(row["rolling_valid_observations"], 1)
            self.assertAlmostEqual(row["load_factor"], 1)
            validate_snapshot(data)

    def test_speed_variability_changes_shaft_harmonics(self):
        baseline = MotorSimulator(seed=8, assets=(config(),))
        variable = MotorSimulator(seed=8, assets=(config(speed_variation_pct=.2),))
        self.assertEqual(baseline.step()["assets"][0]["rpm"],
                         variable.step()["assets"][0]["rpm"])
        normal = baseline.step()["assets"][0]
        changed = variable.step()["assets"][0]
        self.assertGreater(changed["rpm"], normal["rpm"])
        self.assertGreater(changed["shaft_frequency_hz"], normal["shaft_frequency_hz"])

    def test_load_variability_affects_temperature_and_signal(self):
        a = MotorSimulator(seed=8, assets=(config(),)).step()["assets"][0]
        b = MotorSimulator(seed=8, assets=(config(load_variation_pct=.3),)).step()["assets"][0]
        self.assertGreater(b["load_factor"], a["load_factor"])
        self.assertGreater(b["temperature_c"], a["temperature_c"])
        self.assertGreater(b["rms_g"], a["rms_g"])

    def test_noise_and_drift_are_not_machine_faults(self):
        quiet = MotorSimulator(seed=6, assets=(config(sensor_noise_g=0),))
        default = MotorSimulator(seed=6, assets=(config(),))
        self.assertNotEqual(quiet.step()["assets"][0]["rms_g"],
                            default.step()["assets"][0]["rms_g"])
        drift = MotorSimulator(seed=6, assets=(config(sensor_drift_g_per_tick=.001),))
        seq = [drift.step()["assets"][0] for _ in range(4)]
        self.assertEqual([v["sensor_drift_g"] for v in seq], [0, .001, .002, .003])
        self.assertTrue(all(v["sensor_quality"] == "good" for v in seq))

    def test_missing_measurements_are_null_unavailable_and_recover(self):
        motor = config(sensor_missing_onset_tick=2, sensor_missing_duration_ticks=2)
        sim = MotorSimulator(seed=12, assets=(motor,))
        rows = [sim.step()["assets"][0] for _ in range(5)]
        self.assertEqual([r["sensor_quality"] for r in rows],
                         ["good", "missing", "missing", "good", "good"])
        for row in rows[1:3]:
            self.assertEqual(row["health"], "unavailable")
            self.assertIsNone(row["rms_g"])
            self.assertIsNone(row["crest_factor"])
            self.assertIsNone(row["shaft_1x_amplitude_g"])
            self.assertIsNone(row["rolling_rms_mean_g"])
            self.assertIsInstance(row["temperature_c"], float)
            self.assertIsInstance(row["rpm"], float)
        self.assertEqual(rows[2]["rolling_observations"], 3)
        self.assertEqual(rows[2]["rolling_valid_observations"], 1)
        self.assertEqual(rows[3]["rolling_valid_observations"], 2)
        self.assertIsInstance(rows[3]["rms_g"], float)
        self.assertEqual(rows[3]["sensor_quality"], "good")

    def test_first_tick_missing_does_not_become_zero_health(self):
        sim = MotorSimulator(assets=(config(sensor_missing_onset_tick=1,
                                            sensor_missing_duration_ticks=1),))
        first = sim.step()
        row = first["assets"][0]
        validate_snapshot(first)
        self.assertEqual(row["rolling_valid_observations"], 0)
        self.assertIsNone(row["rolling_rms_mean_g"])
        self.assertEqual(row["health"], "unavailable")
        self.assertIn('"rms_g": null', json.dumps(row))
        self.assertEqual(sim.step()["assets"][0]["rolling_valid_observations"], 1)

    def test_outlier_is_suspect_not_machine_fault(self):
        motor = config(sensor_outlier_onset_tick=2, sensor_outlier_duration_ticks=1,
                       sensor_outlier_g=1.5)
        sim = MotorSimulator(seed=2, assets=(motor,))
        rows = [sim.step()["assets"][0] for _ in range(3)]
        self.assertEqual([r["sensor_quality"] for r in rows], ["good", "outlier", "good"])
        self.assertEqual(rows[1]["health"], "suspect")
        self.assertGreater(rows[1]["peak_to_peak_g"], rows[0]["peak_to_peak_g"])
        self.assertEqual(rows[1]["scenario"], "healthy")
        self.assertTrue(rows[1]["sensor_quality_reasons"])

    def test_overlapping_outlier_dropout_prioritizes_missing(self):
        motor = config(sensor_missing_onset_tick=2, sensor_missing_duration_ticks=2,
                       sensor_outlier_onset_tick=2, sensor_outlier_duration_ticks=3,
                       sensor_outlier_g=1)
        sim = MotorSimulator(assets=(motor,))
        rows = [sim.step()["assets"][0] for _ in range(5)]
        self.assertEqual([x["sensor_quality"] for x in rows],
                         ["good", "missing", "missing", "outlier", "good"])
        self.assertIn("masked", " ".join(rows[1]["sensor_quality_reasons"]))

    def test_invalid_config_bounds_and_pairs_rejected(self):
        invalid = [
            {"speed_variation_pct":.201}, {"load_variation_pct":-.01},
            {"sensor_noise_g":.101}, {"sensor_drift_g_per_tick":.002},
            {"speed_variation_pct":True}, {"load_variation_pct":float("nan")},
            {"sensor_missing_duration_ticks":1}, {"sensor_missing_onset_tick":2},
            {"sensor_outlier_duration_ticks":1}, {"sensor_outlier_g":1},
            {"sensor_outlier_onset_tick":2,"sensor_outlier_duration_ticks":1},
            {"sensor_missing_onset_tick":0,"sensor_missing_duration_ticks":1},
            {"sensor_outlier_onset_tick":1,"sensor_outlier_duration_ticks":1,
             "sensor_outlier_g":2.1},
        ]
        for params in invalid:
            with self.subTest(params=params), self.assertRaises(ValueError):
                config(**params)

    def test_configuration_roundtrip_and_schema_rejection(self):
        motor = config(speed_variation_pct=.12,load_variation_pct=.2,sensor_noise_g=.02,
                       sensor_drift_g_per_tick=-.0005,
                       sensor_missing_onset_tick=2,sensor_missing_duration_ticks=1,
                       sensor_outlier_onset_tick=4,sensor_outlier_duration_ticks=1,
                       sensor_outlier_g=.7)
        self.assertEqual(parse_configuration({"assets":[motor.to_dict()]}), (motor,))
        snapshot = MotorSimulator(assets=(motor,)).step()
        validate_snapshot(snapshot)
        tampered = copy.deepcopy(snapshot)
        tampered["assets"][0]["sensor_quality"] = "missing"
        with self.assertRaises(ValueError):
            validate_snapshot(tampered)

    def test_full_replay_and_read_only_snapshot(self):
        motor = config(speed_variation_pct=.1,load_variation_pct=.2,sensor_noise_g=.02,
                       sensor_drift_g_per_tick=.0002,
                       sensor_missing_onset_tick=3,sensor_missing_duration_ticks=2,
                       sensor_outlier_onset_tick=6,sensor_outlier_duration_ticks=1,
                       sensor_outlier_g=1.3)
        with SimulationController(seed=88,assets=(motor,),autostart=False) as controller:
            first = [controller.snapshot()]
            self.assertEqual(controller.snapshot(),first[0])
            for _ in range(7):
                controller.control("step")
                first.append(controller.snapshot())
            controller.control("reset")
            second = [controller.snapshot()]
            for _ in range(7):
                controller.control("step")
                second.append(controller.snapshot())
            self.assertEqual(first, second)
            for item in first:
                validate_snapshot(item)


if __name__ == "__main__":
    unittest.main()
