"""The schema is checked without installing third-party dependencies."""

import copy
import json
from pathlib import Path
import unittest

from motorpulse.schema import (
    SAMPLE_COUNT, SAMPLE_RATE_HZ, SCHEMA_VERSION, SENSOR_UNITS,
    validate_snapshot,
)
from motorpulse.sim import MotorSimulator


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = MotorSimulator(seed=7).step()

    def test_snapshot_valid_and_json_roundtrip(self):
        validate_snapshot(self.snapshot)
        validate_snapshot(json.loads(json.dumps(self.snapshot)))

    def test_unique_events_and_canonical_metadata(self):
        events = self.snapshot["assets"]
        self.assertEqual(len({e["event_id"] for e in events}), len(events))
        self.assertEqual(self.snapshot["schema_version"], SCHEMA_VERSION)
        for event in events:
            self.assertEqual(event["units"], SENSOR_UNITS)
            self.assertEqual(event["sample_rate_hz"], SAMPLE_RATE_HZ)
            self.assertEqual(event["sample_count"], SAMPLE_COUNT)
            self.assertEqual(event["timestamp_utc"], self.snapshot["recorded_at_utc"])

    def test_example_fixture_and_schema_json_present(self):
        root = Path(__file__).resolve().parents[1]
        fixture = json.loads((root / "docs/examples/snapshot-v1.json").read_text())
        schema = json.loads((root / "docs/snapshot.schema.json").read_text())
        validate_snapshot(fixture)
        self.assertEqual(schema["properties"]["schema_version"]["const"], SCHEMA_VERSION)

    def test_reject_missing_event_field(self):
        malformed = copy.deepcopy(self.snapshot)
        del malformed["assets"][0]["event_id"]
        with self.assertRaisesRegex(ValueError, "event_id"):
            validate_snapshot(malformed)

    def test_reject_non_utc_and_naive_timestamps(self):
        for timestamp in ("2026-10-11T12:00:00", "2026-10-11T12:00:00+02:00", "bad-date"):
            with self.subTest(timestamp=timestamp):
                malformed = copy.deepcopy(self.snapshot)
                malformed["recorded_at_utc"] = timestamp
                with self.assertRaises(ValueError):
                    validate_snapshot(malformed)

    def test_reject_bad_version_and_duplicate_ids(self):
        malformed = copy.deepcopy(self.snapshot)
        malformed["schema_version"] = "2.0.0"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            validate_snapshot(malformed)
        malformed = copy.deepcopy(self.snapshot)
        malformed["assets"][1]["event_id"] = malformed["assets"][0]["event_id"]
        with self.assertRaisesRegex(ValueError, "duplicate event_id"):
            validate_snapshot(malformed)

    def test_reject_invalid_health_type(self):
        malformed = copy.deepcopy(self.snapshot)
        malformed["assets"][0]["health"] = []
        with self.assertRaisesRegex(ValueError, "health"):
            validate_snapshot(malformed)

    def test_reject_wrong_units_or_sampling_metadata(self):
        for key, value in (("sample_rate_hz", 0), ("sample_count", -10),
                           ("rms_g", float("nan")), ("units", {"temperature": "F"})):
            with self.subTest(field=key):
                malformed = copy.deepcopy(self.snapshot)
                malformed["assets"][0][key] = value
                with self.assertRaises(ValueError):
                    validate_snapshot(malformed)


if __name__ == "__main__":
    unittest.main()
