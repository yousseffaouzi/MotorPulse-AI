"""Regression tests for MP-019 spectral fixtures and sample metadata."""
import unittest
from random import Random

from motorpulse.schema import SAMPLE_COUNT, SAMPLE_RATE_HZ
from motorpulse.signals import generate_vibration, harmonic_amplitude_g
from motorpulse.sim import MotorSimulator, features


class SignalTests(unittest.TestCase):
    def test_window_duration_and_1x_frequency(self):
        # At 1500 rpm, the shaft frequency is exactly 25 Hz, centered in a 1 Hz DFT bin.
        samples = generate_vibration(1500, "healthy", Random(1))
        self.assertEqual(len(samples), 1024)
        self.assertEqual(SAMPLE_RATE_HZ / SAMPLE_COUNT, 1)  # 1 Hz bins
        self.assertAlmostEqual(harmonic_amplitude_g(samples, 25, SAMPLE_RATE_HZ), 0.12, delta=0.005)
        self.assertLess(harmonic_amplitude_g(samples, 64, SAMPLE_RATE_HZ), 0.005)

    def test_frequency_moves_with_rpm(self):
        a = generate_vibration(1200, "healthy", Random(1))
        b = generate_vibration(1800, "healthy", Random(1))
        self.assertGreater(harmonic_amplitude_g(a, 20, 1024), 0.11)
        self.assertGreater(harmonic_amplitude_g(b, 30, 1024), 0.11)
        self.assertLess(harmonic_amplitude_g(a, 30, 1024), 0.005)
        self.assertLess(harmonic_amplitude_g(b, 20, 1024), 0.005)

    def test_imbalance_increases_1x_component(self):
        baseline = generate_vibration(1500, "healthy", Random(22))
        faulty = generate_vibration(1500, "imbalance", Random(22))
        self.assertGreater(harmonic_amplitude_g(faulty, 25, 1024),
                           4.5 * harmonic_amplitude_g(baseline, 25, 1024))

    def test_misalignment_example_increases_2x(self):
        data = generate_vibration(1500, "misalignment", Random(10))
        self.assertGreater(harmonic_amplitude_g(data, 50, 1024),
                           harmonic_amplitude_g(data, 25, 1024))

    def test_bearing_impulses_generate_high_frequency_structure(self):
        baseline = generate_vibration(1500, "healthy", Random(55))
        bearing = generate_vibration(1500, "bearing_wear", Random(55))
        # Illustrative 4.8x order => nominal 120 Hz component for 25 Hz shaft.
        self.assertGreater(harmonic_amplitude_g(bearing, 120, 1024), 0.20)
        self.assertGreater(features(bearing)["crest_factor"], features(baseline)["crest_factor"])

    def test_deterministic_seed_and_features(self):
        a = generate_vibration(1510, "bearing_wear", Random(987))
        b = generate_vibration(1510, "bearing_wear", Random(987))
        self.assertEqual(a, b)
        self.assertEqual(features(a), features(b))

    def test_reject_aliasing_and_invalid_input(self):
        for params in [
            (1500, "healthy", {"sample_rate_hz": 100}),
            (1500, "bearing_wear", {"sample_rate_hz": 200}),
            (1500, "healthy", {"sample_count": 1}),
            (0, "healthy", {}),
            (float("nan"), "healthy", {}),
            (1500, "unknown_fault", {}),
        ]:
            with self.subTest(case=params):
                rpm, scenario, kwargs = params
                with self.assertRaises(ValueError):
                    generate_vibration(rpm, scenario, Random(1), **kwargs)

    def test_feature_units_and_snapshot_metadata(self):
        snapshot = MotorSimulator(seed=42).step()
        for asset in snapshot["assets"]:
            self.assertEqual(asset["window_duration_s"], 1.0)
            self.assertEqual(asset["sample_rate_hz"], 1024)
            self.assertEqual(asset["sample_count"], 1024)
            self.assertAlmostEqual(asset["shaft_frequency_hz"], asset["rpm"]/60, delta=.001)
            self.assertEqual(asset["units"]["vibration_acceleration"], "g")
        self.assertEqual(snapshot, MotorSimulator(seed=42).step())


if __name__ == "__main__":
    unittest.main()
