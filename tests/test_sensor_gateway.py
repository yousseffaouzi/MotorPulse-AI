from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.sensor_gateway import (
    CANONICAL_UNITS,
    canonical_frame_bytes,
    current_pipeline_sampling_compatible,
    parse_frame_json,
    validate_capture,
    validate_sensor_frame,
    write_report,
)


def _frame(
    *,
    sequence: int = 1,
    uptime: int = 1000,
    timestamp: str = "2026-10-31T12:00:00Z",
    sample_count: int = 4,
) -> dict:
    return {
        "capture_version": "1.0.0",
        "source": "physical_sensor",
        "device_id": "esp32-lab-01",
        "asset_id": "MTR-LAB-01",
        "sequence": sequence,
        "device_uptime_ms": uptime,
        "captured_at_utc": timestamp,
        "sample_rate_hz": 1024,
        "sample_count": sample_count,
        "units": dict(CANONICAL_UNITS),
        "quality": {"vibration": "good", "temperature": "good", "rpm": "good"},
        "acceleration_g": (
            [0.1, -0.1, 0.2, -0.2] if sample_count == 4 else [0.0] * sample_count
        ),
        "temperature_c": 31.25,
        "rpm": 1498.0,
        "provenance": {
            "device_family": "esp32",
            "firmware_version": "0.1.0",
            "accelerometer_model": "lab-accelerometer",
            "temperature_sensor_model": "lab-temperature",
            "rpm_sensor_model": "lab-tachometer",
        },
    }


class SensorFrameTests(unittest.TestCase):
    def test_good_frame_and_current_sampling_compatibility(self):
        frame = _frame()
        validate_sensor_frame(frame)
        self.assertFalse(current_pipeline_sampling_compatible(frame))
        compatible = _frame(sample_count=1024)
        validate_sensor_frame(compatible)
        self.assertTrue(current_pipeline_sampling_compatible(compatible))

    def test_missing_and_outlier_channel_semantics(self):
        frame = _frame()
        frame["quality"]["vibration"] = "missing"
        frame["acceleration_g"] = None
        validate_sensor_frame(frame)
        self.assertFalse(current_pipeline_sampling_compatible(frame))

        bad = deepcopy(frame)
        bad["acceleration_g"] = []
        with self.assertRaisesRegex(ValueError, "must be null"):
            validate_sensor_frame(bad)

        outlier = _frame()
        outlier["quality"]["rpm"] = "outlier"
        outlier["rpm"] = 99999.0
        validate_sensor_frame(outlier)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_constants(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            parse_frame_json('{"capture_version":"1.0.0","capture_version":"1.0.0"}')
        with self.assertRaisesRegex(ValueError, "non-standard JSON constant"):
            parse_frame_json('{"value":NaN}')

    def test_rejects_extra_fields_length_mismatch_and_negative_rpm(self):
        extra = _frame()
        extra["health"] = "normal"
        with self.assertRaisesRegex(ValueError, "fields must match"):
            validate_sensor_frame(extra)

        mismatch = _frame()
        mismatch["acceleration_g"] = [0.0]
        with self.assertRaisesRegex(ValueError, "length must equal"):
            validate_sensor_frame(mismatch)

        negative = _frame()
        negative["rpm"] = -1
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            validate_sensor_frame(negative)


class SensorCaptureTests(unittest.TestCase):
    def _write_frames(
        self, path: Path, frames: list[dict], *, pretty: bool = False
    ) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for frame in frames:
                if pretty:
                    text = json.dumps(
                        frame, ensure_ascii=False, separators=(", ", ": ")
                    )
                else:
                    text = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
                stream.write(text + "\n")

    def test_capture_report_is_reproducible_and_tracks_sequence_gaps(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = [
                _frame(sequence=1, uptime=1000, timestamp="2026-10-31T12:00:00Z"),
                _frame(sequence=3, uptime=3000, timestamp="2026-10-31T12:00:02Z"),
            ]
            compact = root / "compact.jsonl"
            spaced = root / "spaced.jsonl"
            self._write_frames(compact, frames)
            self._write_frames(spaced, frames, pretty=True)
            first = validate_capture(compact)
            second = validate_capture(spaced)
            self.assertEqual(first["records"], 2)
            self.assertEqual(first["sequence_gaps"], 1)
            self.assertNotEqual(first["input_sha256"], second["input_sha256"])
            self.assertEqual(
                first["canonical_frames_sha256"],
                second["canonical_frames_sha256"],
            )
            self.assertEqual(first["claims"]["field_calibrated"], False)

    def test_capture_rejects_nonmonotonic_stream(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            frames = [
                _frame(sequence=2, uptime=2000, timestamp="2026-10-31T12:00:02Z"),
                _frame(sequence=1, uptime=3000, timestamp="2026-10-31T12:00:03Z"),
            ]
            self._write_frames(path, frames)
            with self.assertRaisesRegex(
                ValueError, "sequence is not strictly increasing"
            ):
                validate_capture(path)

    def test_report_is_write_once(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            self._write_frames(path, [_frame()])
            report = validate_capture(path)
            output = Path(tmp) / "report.json"
            write_report(report, output)
            loaded = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(loaded, report)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                write_report(report, output)

    def test_canonical_bytes_ignore_object_key_order(self):
        frame = _frame()
        reversed_frame = dict(reversed(list(frame.items())))
        self.assertEqual(
            canonical_frame_bytes(frame), canonical_frame_bytes(reversed_frame)
        )

    def test_documented_example_is_valid_and_not_pipeline_compatible(self):
        root = Path(__file__).resolve().parents[1]
        report = validate_capture(root / "docs/examples/sensor-frame-v1.jsonl")
        self.assertEqual(report["records"], 1)
        self.assertEqual(report["current_pipeline_sampling_compatible_frames"], 0)
        self.assertTrue(report["claims"]["physical_measurement"])
        self.assertFalse(report["claims"]["field_calibrated"])
        self.assertFalse(report["claims"]["diagnosis"])


if __name__ == "__main__":
    unittest.main()
