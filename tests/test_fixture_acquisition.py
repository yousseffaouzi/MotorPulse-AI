"""Generated fixtures only; no hardware, serial or network operations."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zlib

from motorpulse import fixture_acquisition as transport
from motorpulse.physical_features import extract_capture
from motorpulse.sensor_gateway import canonical_frame_bytes, validate_capture
from test_sensor_gateway import _frame


def _native(sequence=1):
    frame = _frame(
        sequence=sequence,
        uptime=1000 * sequence,
        timestamp=f"2026-10-31T12:00:{sequence:02d}Z",
        sample_count=4000,
    )
    frame["sample_rate_hz"] = 4000
    frame["device_id"] = "fixture-device"
    frame["asset_id"] = "fixture-asset"
    return frame


def _packet(payload):
    header = transport.HEADER.pack(transport.MAGIC, len(payload), zlib.crc32(payload))
    return header + payload


class FixtureAcquisitionTests(unittest.TestCase):
    def test_round_trip_and_native_feature_abstention(self):
        frames = [_native(1), _native(2)]
        batch = b"".join(map(transport.encode_fixture_packet, frames))
        decoded = transport.decode_fixture_batch(batch)
        self.assertEqual(decoded, frames)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture-only.jsonl"
            path.write_bytes(
                b"".join(canonical_frame_bytes(frame) + b"\n" for frame in decoded)
            )
            report = validate_capture(path)
            self.assertEqual(report["records"], 2)
            self.assertEqual(report["sequence_gaps"], 0)
            self.assertEqual(report["current_pipeline_sampling_compatible_frames"], 0)
            rows, _ = extract_capture(path)
            statuses = [row["feature_status"] for row in rows]
            self.assertEqual(statuses, ["abstained"] * 2)

    def test_missing_channel_is_preserved(self):
        frame = _native()
        frame["quality"]["vibration"] = "missing"
        frame["acceleration_g"] = None
        self.assertEqual(
            transport.decode_fixture_batch(transport.encode_fixture_packet(frame)),
            [frame],
        )

    def test_corruption_truncation_and_trailing_bytes(self):
        packet = transport.encode_fixture_packet(_native())
        for bad in (
            b"",
            packet[:5],
            packet[:-1],
            packet + b"x",
            b"BAD!" + packet[4:],
            packet[:-1] + bytes([packet[-1] ^ 1]),
        ):
            with self.subTest(length=len(bad)):
                with self.assertRaises(ValueError):
                    transport.decode_fixture_batch(bad)

    def test_rejects_oversize_and_count_limits(self):
        packet = transport.encode_fixture_packet(_native())
        huge_header = transport.HEADER.pack(
            transport.MAGIC, transport.MAX_PAYLOAD_BYTES + 1, 0
        )
        with self.assertRaisesRegex(ValueError, "payload length"):
            transport.decode_fixture_batch(huge_header)
        with patch.object(transport, "MAX_BATCH_BYTES", len(packet) - 1):
            with self.assertRaisesRegex(ValueError, "batch size"):
                transport.decode_fixture_batch(packet)
        with patch.object(transport, "MAX_PACKETS", 1):
            with self.assertRaisesRegex(ValueError, "packet count"):
                transport.decode_fixture_batch(
                    packet + transport.encode_fixture_packet(_native(2))
                )

    def test_strict_json_and_canonical_payload(self):
        for bad in (
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            b"\xff",
            canonical_frame_bytes(_native()) + b" ",
        ):
            with self.assertRaises(ValueError):
                transport.decode_fixture_batch(_packet(bad))

    def test_native_rate_and_fixture_identity_are_mandatory(self):
        for key, value in (
            ("sample_rate_hz", 1024),
            ("device_id", "real-device"),
            ("asset_id", "real-asset"),
        ):
            frame = _native()
            frame[key] = value
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    transport.encode_fixture_packet(frame)
                with self.assertRaises(ValueError):
                    payload = canonical_frame_bytes(frame)
                    transport.decode_fixture_batch(_packet(payload))

    def test_rejects_gaps_replays_clock_and_provenance_changes(self):
        first = transport.encode_fixture_packet(_native())
        cases = [_native(1), _native(3)]
        for key, value in (
            ("device_id", "fixture-other"),
            ("asset_id", "fixture-other"),
            ("device_uptime_ms", 1000),
            ("captured_at_utc", "2026-10-31T12:00:01Z"),
        ):
            frame = _native(2)
            frame[key] = value
            cases.append(frame)
        changed = _native(2)
        changed["provenance"]["firmware_version"] = "changed"
        cases.append(changed)
        for frame in cases:
            with self.assertRaises(ValueError):
                transport.decode_fixture_batch(
                    first + transport.encode_fixture_packet(frame)
                )
