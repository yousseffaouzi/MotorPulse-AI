"""MP-078 bench plan must stay aligned with the offline capture contract."""

from pathlib import Path
import re
import unittest

from motorpulse.sensor_gateway import REQUIRED_FIELDS


ROOT = Path(__file__).resolve().parents[1]


class Esp32BenchPlanTests(unittest.TestCase):
    def test_capture_mapping_matches_gateway(self):
        plan = (ROOT / "docs" / "ESP32_BENCH_PLAN.md").read_text(encoding="utf-8")
        fields = set(re.findall(r"^\| `([a-z0-9_]+)` \|", plan, re.MULTILINE))
        self.assertEqual(fields, REQUIRED_FIELDS)

    def test_native_rate_and_hardware_review_boundaries(self):
        plan = (ROOT / "docs" / "ESP32_BENCH_PLAN.md").read_text(encoding="utf-8")
        body = " ".join(plan.split())
        for term in (
            "MP-016 remains ON HOLD",
            "not approved for hardware operation",
            "must abstain in MP-058",
            "do not silently store resampled data as raw",
            "No hardware test has been run",
            "Pending independent hardware/safety and metrology review",
        ):
            with self.subTest(term=term):
                self.assertIn(term, body)
        gateway = (ROOT / "docs" / "SENSOR_GATEWAY.md").read_text(encoding="utf-8")
        self.assertIn("ESP32_BENCH_PLAN.md", gateway)
