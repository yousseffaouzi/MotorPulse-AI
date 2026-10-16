"""MP-015 dated synthetic benchmark and demo-media contracts."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "BENCHMARK.md"
DEMO = ROOT / "docs" / "demo" / "benchmark-summary.svg"
GENERATOR = ROOT / "scripts" / "generate_benchmark_report.py"
BENCHMARK_DATE = "2026-10-15"

# The committed snapshot is generated on Python 3.13 only. All supported
# runtimes still validate its static claims; 3.13 additionally proves exact bytes.
# The generated demo is an SVG summary artifact, not a claim that a hosted video exists.


class BenchmarkReportTests(unittest.TestCase):
    def test_report_generator_and_demo_media_are_linked(self):
        self.assertTrue(GENERATOR.is_file())
        self.assertTrue(REPORT.is_file())
        self.assertTrue(DEMO.is_file())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/BENCHMARK.md", readme)
        report = REPORT.read_text(encoding="utf-8")
        self.assertIn("demo/benchmark-summary.svg", report)

    def test_report_is_dated_reproducible_and_synthetic_only(self):
        report = REPORT.read_text(encoding="utf-8")
        for text in (
            f"**Benchmark date:** {BENCHMARK_DATE}",
            "docs/examples/experiment-v1.json",
            "python -m motorpulse.experiment",
            "python scripts/generate_benchmark_report.py",
            "Validation held-out",
            "Test held-out",
            "synthetic-only",
            "whole-run",
            "failure probability",
            "RUL",
            "not field performance",
        ):
            with self.subTest(text=text):
                self.assertIn(text, report)

    def test_demo_media_is_self_contained_svg_with_safety_label(self):
        svg = DEMO.read_text(encoding="utf-8")
        self.assertTrue(svg.startswith("<svg"))
        self.assertNotIn("<script", svg.lower())
        self.assertNotIn("<image", svg.lower())
        self.assertNotIn("xlink:href", svg.lower())
        for text in (
            "MotorPulse AI",
            "Synthetic benchmark",
            "Held-out test",
            "Model",
            "Rules",
            "Not field performance",
        ):
            with self.subTest(text=text):
                self.assertIn(text, svg)

    def test_python_313_regeneration_matches_committed_artifacts(self):
        if sys.version_info[:2] != (3, 13):
            self.skipTest(
                "committed MP-015 snapshot is generated and verified on Python 3.13"
            )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "BENCHMARK.md"
            svg = root / "benchmark-summary.svg"
            cp = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--date",
                    BENCHMARK_DATE,
                    "--markdown",
                    str(markdown),
                    "--svg",
                    str(svg),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertEqual(markdown.read_bytes(), REPORT.read_bytes())
            self.assertEqual(svg.read_bytes(), DEMO.read_bytes())


if __name__ == "__main__":
    unittest.main()
