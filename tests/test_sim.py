import unittest
from motorpulse.sim import MotorSimulator, classify, features


class MotorPulseTest(unittest.TestCase):
    def test_zero_signal(self):
        self.assertEqual(features([0.0] * 8)["rms_g"], 0)

    def test_empty_signal_rejected(self):
        with self.assertRaises(ValueError):
            features([])

    def test_normal_rule(self):
        self.assertEqual(classify(0.12, 40.0, 1.4)[0], "normal")

    def test_critical_rule(self):
        self.assertEqual(classify(0.70, 90.0, 1.2)[0], "critical")

    def test_simulated_assets_and_faults(self):
        row = MotorSimulator().step()
        self.assertEqual(len(row["assets"]), 3)
        self.assertEqual(row["source"], "synthetic")
        self.assertEqual(row["assets"][0]["health"], "normal")
        self.assertEqual(row["assets"][1]["health"], "warning")
        self.assertIn(row["assets"][2]["health"], ("warning", "critical"))

    def test_reproducible_numeric_telemetry(self):
        a = MotorSimulator(seed=3).step()
        b = MotorSimulator(seed=3).step()
        self.assertEqual(a["assets"], b["assets"])


if __name__ == "__main__":
    unittest.main()
