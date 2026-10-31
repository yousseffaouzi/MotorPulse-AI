from __future__ import annotations

import json
from math import pi, sin
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.physical_features import (
    canonical_feature_bytes,
    extract_capture,
    extract_frame_features,
    main,
    write_feature_outputs,
)
from motorpulse.sensor_gateway import CANONICAL_UNITS


def _frame(
    *,
    sequence: int = 1,
    uptime: int = 1000,
    timestamp: str = "2026-10-31T12:00:00Z",
    rpm: float = 1800.0,
    sample_rate_hz: int = 1024,
    sample_count: int = 1024,
) -> dict:
    shaft_hz = rpm / 60 if rpm > 0 else 30.0
    samples = [
        0.5 * sin(2 * pi * shaft_hz * index / sample_rate_hz)
        for index in range(sample_count)
    ]
    return {
        "capture_version": "1.0.0",
        "source": "physical_sensor",
        "device_id": "esp32-lab-01",
        "asset_id": "MTR-LAB-01",
        "sequence": sequence,
        "device_uptime_ms": uptime,
        "captured_at_utc": timestamp,
        "sample_rate_hz": sample_rate_hz,
        "sample_count": sample_count,
        "units": dict(CANONICAL_UNITS),
        "quality": {"vibration": "good", "temperature": "good", "rpm": "good"},
        "acceleration_g": samples,
        "temperature_c": 31.25,
        "rpm": rpm,
        "provenance": {
            "device_family": "esp32",
            "firmware_version": "0.1.0",
            "accelerometer_model": "lab-accelerometer",
            "temperature_sensor_model": "lab-temperature",
            "rpm_sensor_model": "lab-tachometer",
        },
    }


def _write_capture(path: Path, frames: list[dict], *, pretty: bool = False) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for frame in frames:
            separators = (", ", ": ") if pretty else (",", ":")
            stream.write(
                json.dumps(frame, ensure_ascii=False, separators=separators) + "\n"
            )


class PhysicalFeatureFrameTests(unittest.TestCase):
    def test_bin_centered_sine_extracts_expected_non_diagnostic_features(self):
        row = extract_frame_features(_frame())
        self.assertEqual(row["feature_status"], "extracted")
        self.assertEqual(row["feature_status_reasons"], [])
        self.assertAlmostEqual(row["rms_g"], 0.3536, places=4)
        self.assertAlmostEqual(row["peak_to_peak_g"], 1.0, places=4)
        self.assertAlmostEqual(row["crest_factor"], 1.4142, places=4)
        self.assertEqual(row["spectral_bin_hz"], 1.0)
        self.assertEqual(row["dominant_frequency_hz"], 30.0)
        self.assertAlmostEqual(row["shaft_1x_amplitude_g"], 0.5, places=4)
        self.assertAlmostEqual(row["shaft_2x_amplitude_g"], 0.0, places=4)
        self.assertAlmostEqual(row["band_80_400_rms_g"], 0.0, places=4)
        self.assertNotIn("acceleration_g", row)
        self.assertNotIn("health", row)
        self.assertNotIn("scenario", row)

    def test_non_good_channel_abstains_without_inventing_features(self):
        frame = _frame()
        frame["quality"]["vibration"] = "missing"
        frame["acceleration_g"] = None
        row = extract_frame_features(frame)
        self.assertEqual(row["feature_status"], "abstained")
        self.assertIn("vibration quality is missing", row["feature_status_reasons"])
        self.assertIsNone(row["rms_g"])
        self.assertIsNone(row["shaft_1x_amplitude_g"])
        self.assertEqual(row["temperature_c"], 31.25)
        self.assertEqual(row["rpm"], 1800.0)

        outlier = _frame()
        outlier["quality"]["temperature"] = "outlier"
        row = extract_frame_features(outlier)
        self.assertEqual(row["feature_status"], "abstained")
        self.assertIn("temperature quality is outlier", row["feature_status_reasons"])

    def test_incompatible_sampling_and_stopped_motor_abstain(self):
        sampling = extract_frame_features(_frame(sample_count=512))
        self.assertEqual(sampling["feature_status"], "abstained")
        self.assertIn("1024 Hz and 1024 samples", sampling["feature_status_reasons"][0])

        stopped = extract_frame_features(_frame(rpm=0.0))
        self.assertEqual(stopped["feature_status"], "abstained")
        self.assertIn(
            "rpm must be positive for shaft-referenced spectral features",
            stopped["feature_status_reasons"],
        )
        self.assertIsNone(stopped["spectral_window"])

    def test_input_frame_hash_changes_when_measurement_changes(self):
        first = extract_frame_features(_frame())
        changed = _frame()
        changed["temperature_c"] = 32.0
        second = extract_frame_features(changed)
        self.assertNotEqual(first["input_frame_sha256"], second["input_frame_sha256"])


class PhysicalFeatureCaptureTests(unittest.TestCase):
    def test_semantically_identical_capture_has_stable_feature_digest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = [
                _frame(sequence=1, uptime=1000, timestamp="2026-10-31T12:00:00Z"),
                _frame(sequence=2, uptime=2000, timestamp="2026-10-31T12:00:01Z"),
            ]
            compact = root / "compact.jsonl"
            spaced = root / "spaced.jsonl"
            _write_capture(compact, frames)
            _write_capture(spaced, frames, pretty=True)
            compact_rows, compact_report = extract_capture(compact)
            spaced_rows, spaced_report = extract_capture(spaced)
            self.assertNotEqual(
                compact_report["input_sha256"], spaced_report["input_sha256"]
            )
            self.assertEqual(
                compact_report["canonical_frames_sha256"],
                spaced_report["canonical_frames_sha256"],
            )
            self.assertEqual(
                compact_report["features_sha256"], spaced_report["features_sha256"]
            )
            self.assertEqual(compact_rows, spaced_rows)
            self.assertEqual(compact_report["feature_status_counts"], {"extracted": 2})

    def test_outputs_are_write_once_waveform_free_and_hash_bound(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / "capture.jsonl"
            _write_capture(capture, [_frame()])
            rows, report = extract_capture(capture)
            features = root / "features.jsonl"
            report_path = root / "report.json"
            write_feature_outputs(rows, report, features, report_path)

            feature_bytes = features.read_bytes()
            self.assertEqual(
                feature_bytes, b"".join(canonical_feature_bytes(row) + b"\n" for row in rows)
            )
            written_row = json.loads(feature_bytes.decode("utf-8"))
            self.assertNotIn("acceleration_g", written_row)
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")), report
            )
            self.assertFalse(report["claims"]["field_calibrated"])
            self.assertFalse(report["claims"]["training_authorized"])
            self.assertFalse(report["claims"]["model_scoring_authorized"])
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                write_feature_outputs(rows, report, features, root / "other-report.json")

    def test_cli_writes_both_outputs_and_refuses_same_path(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / "capture.jsonl"
            _write_capture(capture, [_frame()])
            features = root / "features.jsonl"
            report = root / "report.json"
            self.assertEqual(
                main(
                    [
                        str(capture),
                        "--out-features",
                        str(features),
                        "--out-report",
                        str(report),
                    ]
                ),
                0,
            )
            self.assertTrue(features.is_file())
            self.assertTrue(report.is_file())

            rows, summary = extract_capture(capture)
            same = root / "same.json"
            with self.assertRaisesRegex(ValueError, "must be different"):
                write_feature_outputs(rows, summary, same, same)

    def test_documentation_keeps_physical_feature_boundary_explicit(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/PHYSICAL_FEATURES.md").read_text(encoding="utf-8")
        for phrase in (
            "does not score",
            "not field calibration",
            "No serial",
            "no PLC",
            "no RUL",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
