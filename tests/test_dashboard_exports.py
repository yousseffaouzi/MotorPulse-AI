"""MP-044 contracts for local, simulation-labelled dashboard exports."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
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

    @unittest.skipUnless(shutil.which("node"), "Optional JavaScript engine not installed")
    def test_csv_formula_prefix_and_quotes_execute_in_v8(self):
        contract = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync(process.argv[1], 'utf8');
class Element {
  constructor() {
    this.value=''; this.disabled=false; this.options=[]; this.children=[];
    this.textContent=''; this.classList={toggle:()=>{}};
  }
  addEventListener() {}
  appendChild(child) {this.children.push(child); return child;}
  replaceChildren(...children) {this.children=children;}
  setAttribute() {}
}
const elements = {};
global.document = {
  getElementById(id) {return elements[id] ||= new Element();},
  createElement() {return new Element();},
  createElementNS() {return new Element();},
  createDocumentFragment() {return new Element();},
  body: new Element(),
};
global.window = {};
const modified = code.replace(
  '  void reloadSessions({preferCurrent:true});',
  '  window.__exportHooks={csvCell};'
);
assert.notEqual(modified, code, 'expected export hook anchor');
vm.runInThisContext(modified, {filename:'history.js'});
const csvCell = window.__exportHooks.csvCell;
assert.equal(csvCell('safe'), '"safe"');
assert.equal(csvCell('a"b'), '"a""b"');
for (const value of ['=2+2', '+cmd', '-1', '@name']) {
  assert.equal(csvCell(value)[1], "'", value + ' must be neutralized');
}
console.log('MP-044 CSV escaping: OK');
"""
        check = subprocess.run(
            ["node", "-e", contract, str(JS)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(check.returncode, 0, check.stdout + "\n" + check.stderr)
        self.assertIn("MP-044 CSV escaping: OK", check.stdout)


if __name__ == "__main__":
    unittest.main()
