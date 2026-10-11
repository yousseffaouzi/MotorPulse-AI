"""MP-028: native-rate Hann single-tone checks on invented ASCII data."""
from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse.ims_tone import native_hann_tone

FILENAME = "2004.02.12.10.32.39"


def wave(folder: Path, *, n: int = 64, fs: int = 64, hz: float = 8) -> Path:
    source = folder / FILENAME
    source.write_text("".join(
        f"{3 + math.sin(2*math.pi*hz*i/fs):.12f} "
        f"{0.5*math.sin(2*math.pi*hz*i/fs):.12f}\n" for i in range(n)
    ), encoding="ascii")
    return source


class NativeHannToneTests(unittest.TestCase):
    def test_known_tone_and_dc_detrending(self):
        with TemporaryDirectory() as tmp:
            src = wave(Path(tmp))
            result = native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                      expected_channels=2, requested_hz=8, value_unit="V")
            self.assertEqual(result["analyzed_frequency_hz"], 8)
            self.assertEqual(result["frequency_bin_hz"], 1)
            self.assertEqual(result["nyquist_hz_declared"], 32)
            self.assertEqual(result["window"], "periodic_hann")
            self.assertEqual(result["value_unit"], "V")
            self.assertAlmostEqual(result["amplitudes"][0]["peak_amplitude_native"], 1, places=9)
            self.assertAlmostEqual(result["amplitudes"][1]["peak_amplitude_native"], .5, places=9)
            self.assertFalse(result["resampling_applied"])
            self.assertEqual(len(result["source_sha256"]), 64)

    def test_off_bin_hann_is_approximate(self):
        with TemporaryDirectory() as tmp:
            src = wave(Path(tmp), hz=8.3)
            r = native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                 expected_channels=2, requested_hz=8.3)
            self.assertEqual(r["analyzed_frequency_hz"],8)
            self.assertGreater(r["amplitudes"][0]["peak_amplitude_native"],.85)
            self.assertLess(r["amplitudes"][0]["peak_amplitude_native"],1.02)
            self.assertEqual(r["aliasing_assessment"], "unknown; upstream acquisition was not validated")

    def test_reject_out_of_band_or_unresolvable_bins(self):
        with TemporaryDirectory() as tmp:
            src = wave(Path(tmp))
            for hz in (0, -1, .1, 32, 40, float("nan"), float("inf"), True):
                with self.subTest(hz=hz), self.assertRaises(ValueError):
                    native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                     expected_channels=2, requested_hz=hz)

    def test_reject_invalid_units_sample_sizes_and_rates(self):
        with TemporaryDirectory() as tmp:
            src = wave(Path(tmp))
            for options in ({"sample_rate_hz":0}, {"sample_rate_hz":True},
                            {"sample_rate_hz":1_000_001}, {"expected_samples":2},
                            {"expected_samples":32769}, {"expected_channels":0},
                            {"expected_channels":17}, {"value_unit":"kilograms"}):
                kwargs = {"sample_rate_hz":64, "expected_samples":64,
                          "expected_channels":2, "requested_hz":8}
                kwargs.update(options)
                with self.subTest(options=options), self.assertRaises(ValueError):
                    native_hann_tone(src, **kwargs)

    def test_bounded_nonnumeric_and_wrong_rows(self):
        with TemporaryDirectory() as tmp:
            src = wave(Path(tmp))
            src.write_text("bad 1\n"*64, encoding="ascii")
            with self.assertRaisesRegex(ValueError,"invalid numeric"):
                native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                 expected_channels=2, requested_hz=8)
            src.write_text("1 2\n"*63, encoding="ascii")
            with self.assertRaisesRegex(ValueError,"unexpected end"):
                native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                 expected_channels=2, requested_hz=8)
            src.write_text("1 2\n"*65, encoding="ascii")
            with self.assertRaisesRegex(ValueError,"extra rows"):
                native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                 expected_channels=2, requested_hz=8)
            src.write_text("1 nan\n"*64, encoding="ascii")
            with self.assertRaisesRegex(ValueError,"nonfinite"):
                native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                 expected_channels=2, requested_hz=8)

    def test_file_size_limit_and_symlink_rejected(self):
        with TemporaryDirectory() as tmp:
            src = wave(Path(tmp))
            with patch("motorpulse.ims_tone.MAX_FILE_BYTES", 1):
                with self.assertRaisesRegex(ValueError,"size limit"):
                    native_hann_tone(src, sample_rate_hz=64, expected_samples=64,
                                     expected_channels=2, requested_hz=8)
            alias = Path(tmp) / "2004.02.12.10.32.40"
            try:
                alias.symlink_to(src)
            except (OSError, NotImplementedError):
                return
            with self.assertRaisesRegex(ValueError,"symlink"):
                native_hann_tone(alias, sample_rate_hz=64, expected_samples=64,
                                 expected_channels=2, requested_hz=8)


if __name__ == "__main__":
    unittest.main()
