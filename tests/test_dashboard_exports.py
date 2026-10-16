"""MP-044 contracts for local, simulation-labelled dashboard exports."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "motorpulse" / "web" / "index.html"
JS = ROOT / "motorpulse" / "web" / "history.js"


class DashboardExportContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.script = JS.read_text(encoding="utf-8")

    def test_history_panel_has_bounded_export_controls(self):
        for control in (
            'id="history-export-csv"',
            'id="history-export-rms"',
            'id="history-export-temp"',
            'id="history-export-rpm"',
        ):
            with self.subTest(control=control):
                self.assertIn(control, self.html)
        self.assertIn("Export loaded page", self.html)
        self.assertIn("synthetic simulation", self.html.lower())

    def test_exports_are_client_side_only_and_use_loaded_rows(self):
        script = self.script
        self.assertIn("let currentRows = [];", script)
        self.assertIn("function exportCsv()", script)
        self.assertIn("function exportSvg(metric)", script)
        self.assertIn("new Blob", script)
        self.assertIn("URL.createObjectURL", script)
        self.assertNotIn("/api/export", script)
        self.assertNotIn("fetch('/api/history/export", script)

    def test_csv_contract_is_simulation_labelled_and_formula_safe(self):
        script = self.script
        for term in (
            "MotorPulse AI synthetic simulation export",
            "session_id",
            "asset_id",
            "timestamp_utc",
            "rms_g",
            "temperature_c",
            "rpm",
            "sensor_quality",
            "health",
            "csvCell",
        ):
            with self.subTest(term=term):
                self.assertIn(term, script)
        self.assertIn("^[=+\\-@]", script)

    def test_svg_contract_clones_rendered_chart_and_adds_simulation_title(self):
        script = self.script
        self.assertIn("cloneNode(true)", script)
        self.assertIn("Synthetic simulation chart", script)
        self.assertIn("xmlns", script)
        self.assertIn("image/svg+xml;charset=utf-8", script)
        self.assertIn("XMLSerializer", script)

    def test_export_buttons_follow_loaded_page_state(self):
        script = self.script
        self.assertIn("function setExportReady(ready)", script)
        self.assertIn("currentRows = rows;", script)
        self.assertIn("setExportReady(count > 0)", script)
        self.assertIn("currentRows = [];", script)
        self.assertIn("setExportReady(false)", script)


if __name__ == "__main__":
    unittest.main()
