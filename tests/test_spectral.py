"""MP-023: spectral numerical fixtures and tick-only rolling feature contracts."""
import copy
import math
from random import Random
import unittest

from motorpulse.controller import SimulationController
from motorpulse.scenarios import AssetScenario
from motorpulse.schema import validate_snapshot
from motorpulse.signals import generate_vibration
from motorpulse.sim import MotorSimulator
from motorpulse.spectral import _fft_radix2, spectral_features, ROLLING_WINDOW_TICKS


class SpectralTests(unittest.TestCase):
    def test_fft_matches_direct_small_reference(self):
        samples = [complex(x) for x in (0, 1, 0, -1, 0, 1, 0, -1)]
        fft = _fft_radix2(samples)
        for k in range(8):
            expected = sum(v * complex(math.cos(-2*math.pi*k*i/8), math.sin(-2*math.pi*k*i/8))
                           for i,v in enumerate(samples))
            self.assertAlmostEqual(fft[k].real, expected.real, places=10)
            self.assertAlmostEqual(fft[k].imag, expected.imag, places=10)

    def test_exact_bin_centered_sine_1x(self):
        samples = [0.5 * math.sin(2*math.pi*25*i/1024) for i in range(1024)]
        result = spectral_features(samples, 1500)
        self.assertEqual(result["spectral_window"], "hann")
        self.assertEqual(result["spectral_bin_hz"], 1.0)
        self.assertEqual(result["dominant_frequency_hz"], 25.0)
        self.assertAlmostEqual(result["shaft_1x_amplitude_g"], 0.5, delta=1e-3)
        self.assertLess(result["shaft_2x_amplitude_g"], 1e-3)
        self.assertLess(result["band_80_400_rms_g"], 1e-3)

    def test_misalignment_harmonic_2x(self):
        samples = [0.1*math.sin(2*math.pi*25*i/1024)+0.4*math.sin(2*math.pi*50*i/1024)
                   for i in range(1024)]
        result = spectral_features(samples, 1500)
        self.assertAlmostEqual(result["shaft_1x_amplitude_g"], .1, delta=.002)
        self.assertAlmostEqual(result["shaft_2x_amplitude_g"], .4, delta=.002)
        self.assertEqual(result["dominant_frequency_hz"], 50)

    def test_band_power_g_rms_parseval(self):
        samples = [.5*math.sin(2*math.pi*120*i/1024) for i in range(1024)]
        result = spectral_features(samples, 1500)
        self.assertAlmostEqual(result["band_80_400_rms_g"], .5/math.sqrt(2), delta=.001)
        self.assertEqual(result["dominant_frequency_hz"], 120)

    def test_dc_detrended(self):
        result = spectral_features([0.15]*1024, 1500)
        self.assertEqual(result["dominant_frequency_hz"], 0)
        self.assertEqual(result["shaft_1x_amplitude_g"], 0)
        self.assertEqual(result["band_80_400_rms_g"], 0)

    def test_off_bin_frequency_1x_robust(self):
        samples = [.34 * math.sin(2*math.pi*24.65*i/1024) for i in range(1024)]
        result = spectral_features(samples, 1479)
        self.assertAlmostEqual(result["dominant_frequency_hz"],25,delta=1)
        self.assertGreater(result["shaft_1x_amplitude_g"], .26)
        self.assertLess(result["shaft_1x_amplitude_g"], .35)

    def test_repeat_and_no_mutation(self):
        rng=Random(5)
        original=[rng.uniform(-.9,.9) for _ in range(1024)]
        before=original[:]
        self.assertEqual(spectral_features(original,1500),spectral_features(original,1500))
        self.assertEqual(original,before)

    def test_invalid_inputs(self):
        xs=[0]*1024
        for samples,rpm,fs in [([0]*63,1500,1024), ([0]*0,1500,1024),
             ([0]*16384,1500,1024), ([0]*1023,1500,1024),
             ([float("nan")]*1024,1500,1024),([float("inf")]*1024,1500,1024),
             (xs,0,1024),(xs,float("inf"),1024), (xs,1500,800),
             (xs,1500,False),(xs,20000,1024)]:
            with self.subTest(n=len(samples),rpm=rpm,fs=fs):
                with self.assertRaises(ValueError):
                    spectral_features(samples,rpm,fs)


class SimulatorSpectralTests(unittest.TestCase):
    def test_fault_signatures_separate_examples(self):
        assets = (
            AssetScenario("MTR-01", "Normal"),
            AssetScenario("MTR-02", "Imbalance", "imbalance", 1),
            AssetScenario("MTR-03", "Misalignment", "misalignment", 1),
            AssetScenario("MTR-04", "Bearing", "bearing_wear", 1),
        )
        rows = {r["asset_id"]: r for r in MotorSimulator(seed=42, assets=assets).step()["assets"]}
        self.assertGreater(rows["MTR-02"]["shaft_1x_amplitude_g"],
                           3 * rows["MTR-01"]["shaft_1x_amplitude_g"])
        self.assertGreater(rows["MTR-03"]["shaft_2x_amplitude_g"],
                           rows["MTR-03"]["shaft_1x_amplitude_g"])
        self.assertGreater(rows["MTR-04"]["band_80_400_rms_g"],
                           3 * rows["MTR-01"]["band_80_400_rms_g"])

    def test_rolling_uses_only_recent_simulation_ticks(self):
        sim = MotorSimulator(seed=91)
        sequences = {a.asset_id: [] for a in sim.assets}
        for tick in range(1, 9):
            snapshot = sim.step()
            validate_snapshot(snapshot)
            for row in snapshot["assets"]:
                values = sequences[row["asset_id"]]
                values.append((row["rms_g"], row["temperature_c"]))
                tail = values[-ROLLING_WINDOW_TICKS:]
                self.assertEqual(row["rolling_window_ticks"], ROLLING_WINDOW_TICKS)
                self.assertEqual(row["rolling_observations"], min(tick, ROLLING_WINDOW_TICKS))
                self.assertAlmostEqual(row["rolling_rms_mean_g"],
                                       round(sum(x[0] for x in tail)/len(tail), 4), places=4)
                self.assertAlmostEqual(row["rolling_temperature_mean_c"],
                                       round(sum(x[1] for x in tail)/len(tail), 4), places=4)

    def test_repeated_reads_do_not_update_rolling_features(self):
        with SimulationController(autostart=False, seed=15) as controller:
            before = controller.snapshot()
            self.assertEqual(before, controller.snapshot())
            self.assertEqual(before["assets"][0]["rolling_observations"], 1)
            controller.control("step")
            after = controller.snapshot()
            self.assertEqual(after["assets"][0]["rolling_observations"], 2)
            self.assertEqual(after, controller.snapshot())

    def test_reset_replays_spectrum_and_rolling(self):
        with SimulationController(autostart=False, seed=4) as controller:
            sequence = [controller.snapshot()]
            for _ in range(6):
                controller.control("step")
                sequence.append(controller.snapshot())
            controller.control("reset")
            replay = [controller.snapshot()]
            for _ in range(6):
                controller.control("step")
                replay.append(controller.snapshot())
            self.assertEqual(sequence, replay)

    def test_validator_rejects_bad_new_fields(self):
        original = MotorSimulator().step()
        for field, value in (
            ("spectral_window", "rectangular"), ("dominant_frequency_hz", -1),
            ("band_80_400_rms_g", float("nan")), ("rolling_window_ticks", 0),
            ("rolling_observations", 6), ("spectral_bin_hz", 6.5),
        ):
            with self.subTest(field=field):
                invalid = copy.deepcopy(original)
                invalid["assets"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_snapshot(invalid)


if __name__ == "__main__":
    unittest.main()
