"""MP-013: packaged responsive SVG trend UI and real localhost SQLite history."""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from motorpulse.__main__ import MotorPulseServer, ROOT
from motorpulse.scenarios import AssetScenario

ROOT_REPO = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"
JS = ROOT / "history.js"


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = []
        self.labels = []
        self.scripts = []
        self.aria = {}

    def handle_starttag(self, name, attrs):
        props = dict(attrs)
        self.tags.append((name, props))
        if "id" in props:
            self.ids.append(props["id"])
            self.aria[props["id"]] = props
        if name == "label" and "for" in props:
            self.labels.append(props["for"])
        if name == "script":
            self.scripts.append(props)


class HistoryMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.script = JS.read_text(encoding="utf-8")
        cls.dom = Tags()
        cls.dom.feed(cls.html)

    def test_three_distinct_chart_svgs_and_accessible_headings(self):
        for suffix in ("rms", "temp", "rpm"):
            self.assertIn("history-" + suffix, self.dom.ids)
            self.assertIn("history-" + suffix + "-heading", self.dom.ids)
            self.assertEqual(self.dom.aria["history-" + suffix]["role"], "img")
            self.assertEqual(self.dom.aria["history-" + suffix]["aria-labelledby"],
                             "history-" + suffix + "-heading")
        self.assertEqual(len([props for tag, props in self.dom.tags
                              if tag == "figure" and props.get("class") == "history-figure"]), 3)

    def test_filter_controls_all_have_programmatic_labels(self):
        ids = ("history-session", "history-asset", "history-start", "history-end",
               "history-limit")
        for name in ids:
            self.assertIn(name, self.dom.ids)
            self.assertIn(name, self.dom.labels)
        self.assertIn("history-filters", self.dom.ids)
        self.assertIn("history-newer", self.dom.ids)
        self.assertIn("history-older", self.dom.ids)
        self.assertIn("history-latest", self.dom.ids)
        self.assertIn("history-apply", self.dom.ids)

    def test_accessible_data_table_status_and_missing_value_caveats(self):
        self.assertEqual(self.dom.aria["history-message"]["role"], "status")
        self.assertEqual(self.dom.aria["history-message"]["aria-live"], "polite")
        self.assertEqual(self.dom.aria["history-page"]["aria-live"], "polite")
        # Only the expandable numeric readings table has six columns.
        # MP-042 adds a separate incident review table with its own headings.
        readings = Tags()
        readings.feed(self.html.split('id="history-data-details"', 1)[1])
        self.assertEqual(len([p for tag,p in readings.tags
                              if tag == "th" and p.get("scope") == "col"]), 6)
        self.assertIn("history-table", self.dom.ids)
        self.assertTrue(any(tag == "details" for tag,_ in self.dom.tags))
        self.assertTrue(any(tag == "summary" for tag,_ in self.dom.tags))
        self.assertIn("missing values shown as unavailable",self.html)
        self.assertIn("not measured physical degradation",self.html)

    def test_responsive_layout_and_offline_packaged_script_tag(self):
        self.assertEqual([p["src"] for p in self.dom.scripts if "src" in p],
                         ["/history.js", "/incidents.js"])
        self.assertTrue(any(p.get("defer") is None for p in self.dom.scripts if "src" in p))
        self.assertIn("@media(max-width:650px)",self.html)
        self.assertIn("minmax(min(100%,320px),1fr)",self.html)
        import tomllib
        with (ROOT_REPO/"pyproject.toml").open("rb") as stream:
            project=tomllib.load(stream)
        package_data=project["tool"]["setuptools"]["package-data"]["motorpulse"]
        self.assertIn("web/history.js",package_data)

    def test_good_sensor_vibration_is_separate_from_other_indicators(self):
        script=self.script
        self.assertIn("event.sensor_quality !== 'good'",script)
        self.assertIn("if(value===null) {flush();return;}",script)
        self.assertIn("segment=[]",script)
        self.assertIn("metric.gateQuality",script)
        self.assertIn("gateQuality:false",script)
        self.assertIn("typeof value === 'number' && Number.isFinite(value)",script)
        self.assertNotIn("cdn.",script.lower())

    def test_all_remote_data_is_escaped_or_text_not_html(self):
        self.assertIn("option.textContent = text",self.script)
        self.assertIn("td.textContent = String(value)",self.script)
        self.assertIn("message.textContent = text",self.script)
        self.assertIn("URLSearchParams",self.script)
        self.assertNotIn("innerHTML",self.script)
        self.assertNotIn("eval(",self.script)

    def test_readonly_history_requests_are_bounded_and_manually_refreshable(self):
        self.assertIn("/api/history/sessions?limit=100",self.script)
        self.assertIn("/api/history/events?",self.script)
        self.assertIn("const MAX_POINTS = 100",self.script)
        self.assertIn("if (cursors[position] !== null)",self.script)
        self.assertIn("resetPage();",self.script)
        self.assertIn("request!==token",self.script)
        self.assertIn("History is disabled.",self.script)
        self.assertIn("session_id:sessions.value, asset_id:assets.value",self.script)

    def test_live_control_and_runtime_scenario_changes_sync_history(self):
        self.assertIn("window.MotorPulseHistory.reloadSessions({preferCurrent:true})",self.html)
        self.assertIn("window.MotorPulseHistory.refresh()",self.html)
        self.assertIn("const configRows=",self.html)
        self.assertIn("id=\"runtime-form\"",self.html)
        self.assertIn("data-action=\"reset\"",self.html)


NODE_CONTRACT = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync(process.argv[1],'utf8');
new Function(code);
const elements = {};
class Element {
  constructor(tag) {
    this.tagName=tag;
    this.attributes={};
    this.children=[];
    this.value='';
    this.disabled=false;
    this.textContent='';
    this.classList={toggle:()=>{}};
    this.options=[];
  }
  addEventListener() {}
  appendChild(child) {this.children.push(child);return child;}
  replaceChildren(...children) {this.children=children;}
  setAttribute(name,value) {this.attributes[name]=String(value);}
}
global.document = {
  getElementById(id) {return elements[id] ||= new Element(id);},
  createElement(name) {return new Element(name);},
  createElementNS(_ns,name) {return new Element(name);},
  createDocumentFragment() {return new Element('fragment');}
};
global.window = {};
const modified = code.replace('  void reloadSessions({preferCurrent:true});',
  '  window.__hooks={utcMicros,numeric,draw,buildTable,render,filters,metrics};');
assert.notEqual(modified,code,'expected chart hook anchor');
vm.runInThisContext(modified,{filename:'history.js'});
const f=window.__hooks;
assert.equal(f.utcMicros('2026-01-01T00:00:00.000002Z') -
             f.utcMicros('2026-01-01T00:00:00.000001+00:00'),1);
for (const bad of ['2026-01-01T00:00:00+01:00','2026-01-01','nonsense']) {
  assert.throws(()=>f.utcMicros(bad));
}
const e=(n,quality,rms)=>({
  timestamp_utc:'2026-01-01T00:00:00.00000'+n+'Z',
  sensor_quality:quality, rms_g:rms,temperature_c:50+n,rpm:1470+n,
  health:quality==='good'?'normal':'suspect',
});
const rows=[e(5,'good',.5),e(4,'outlier',.8),e(3,'missing',null),
            e(2,'good',.2),e(1,'good',.1)].map(event=>({event}));
const vib=f.metrics[0],temp=f.metrics[1],rpm=f.metrics[2];
assert.equal(f.numeric(rows[1].event,vib),null,'exclude suspect waveform');
assert.equal(f.numeric(rows[1].event,temp),54,'temperature retained');
assert.equal(f.numeric(rows[2].event,rpm),1473,'speed retained');
f.draw(vib,rows);
const plot=elements['history-rms'].children;
assert.equal(plot.filter(n=>n.tagName==='polyline').length,1,
  'only first two consecutive eligible points form a continuous trace');
assert.equal(plot.filter(n=>n.tagName==='circle').length,1,
  'last valid point after suspect/missing interval is isolated');
assert.match(elements['history-rms-summary'].textContent,/3 of 5 plotted/);
assert.match(elements['history-rms-summary'].textContent,/2 unavailable/);
f.draw(temp,rows);
assert.equal(elements['history-temp'].children.filter(n=>n.tagName==='polyline').length,1,
  'non-vibration temperature readings remain continuous');
f.buildTable(rows);
assert.equal(elements['history-table'].children[0].children.length,5);
assert.equal(elements['history-table'].children[0].children[2].children[1].textContent,'Unavailable');
assert.equal(elements['history-table'].children[0].children[1].children[4].textContent,'outlier');
f.draw(vib,[]);
assert.match(elements['history-rms-summary'].textContent,/No recorded data/);
console.log('Node V8 test: microsecond timestamps, censor-free source quality gaps, axes and accessible table: OK');
"""


class ChartJavascriptExecutionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Optional JavaScript engine not installed")
    def test_client_rendering_and_microsecond_gap_semantics_in_v8(self):
        check = subprocess.run(["node","-e",NODE_CONTRACT,str(JS)],cwd=ROOT_REPO,
                               capture_output=True,text=True,timeout=15,check=False)
        self.assertEqual(check.returncode,0,check.stdout+"\n"+check.stderr)
        self.assertIn("source quality gaps",check.stdout)

    @unittest.skipUnless(shutil.which("node"), "Optional JavaScript engine not installed")
    def test_packaged_script_has_valid_javascript_syntax(self):
        check=subprocess.run(["node","--check",str(JS)],capture_output=True,text=True,
                             timeout=15,check=False)
        self.assertEqual(check.returncode,0,check.stderr)


class HistoryDashboardHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory()
        cls.server=MotorPulseServer(("127.0.0.1",0),autostart=False,
            assets=(AssetScenario("MTR-01","Normal motor"),
                    AssetScenario("MTR-02","Test load","overload",1.0),
                    AssetScenario("MTR-03","Missing vibration",sensor_missing_onset_tick=2,
                                  sensor_missing_duration_ticks=1,
                                  sensor_outlier_onset_tick=3,
                                  sensor_outlier_duration_ticks=1,sensor_outlier_g=.8)),
            step_seconds=.000001,
            database_path=Path(cls.temp.name)/"history.sqlite3")
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        for _ in range(4):
            cls.server.controller.control("step")
        cls.origin=f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def get(self,path):
        try:
            response=urlopen(self.origin+path,timeout=3)
        except HTTPError as error:
            response=error
        with response:
            return response.status,response.headers,response.read()

    def test_served_dashboard_and_local_script_without_external_cdns(self):
        code,headers,raw=self.get("/")
        self.assertEqual(code,200)
        self.assertIn(b'/history.js',raw)
        code,headers,script=self.get("/history.js")
        self.assertEqual(code,200)
        self.assertIn(b"svg",script.lower())
        self.assertIn(b"/api/history/events?",script)
        self.assertIn("javascript",headers["Content-Type"])
        self.assertEqual(script,JS.read_bytes())

    def test_live_status_and_history_api_roundtrip_for_selected_motor(self):
        status=json.loads(self.get("/api/status")[2])
        self.assertEqual(status["tick"],5)
        session=status["session_id"]
        sessions=json.loads(self.get("/api/history/sessions?limit=100")[2])
        self.assertEqual(sessions["items"][0]["session_id"],session)
        self.assertEqual(len(sessions["items"][0]["configuration"]["assets"]),3)
        events=json.loads(self.get(
            "/api/history/events?limit=100&session_id="+session+"&asset_id=MTR-01")[2])
        self.assertEqual(events["page"]["count"],5)
        self.assertEqual([r["event"]["event_id"].split(":")[-1]
                          for r in events["items"]],["5","4","3","2","1"])

    def test_sensor_dropout_is_null_not_synthetic_interpolation(self):
        records=json.loads(self.get("/api/history/events?asset_id=MTR-03")[2])["items"]
        by_tick={int(r["event"]["event_id"].rsplit(":",1)[-1]):r["event"] for r in records}
        self.assertEqual(by_tick[2]["sensor_quality"],"missing")
        self.assertIsNone(by_tick[2]["rms_g"])
        self.assertEqual(by_tick[3]["sensor_quality"],"outlier")
        self.assertIsInstance(by_tick[3]["rms_g"],float)
        self.assertTrue(all(isinstance(row["temperature_c"],float) for row in by_tick.values()))

    def test_utc_time_and_session_filters_match_rendered_page(self):
        uri=("/api/history/events?asset_id=MTR-02&limit=25"
             "&start_utc=2026-01-01T00%3A00%3A00.000002Z"
             "&end_utc=2026-01-01T00%3A00%3A00.000004Z")
        code,_,raw=self.get(uri)
        self.assertEqual(code,200)
        records=json.loads(raw)["items"]
        self.assertEqual(len(records),3)
        self.assertTrue(all(r["event"]["asset_id"]=="MTR-02" for r in records))
        self.assertEqual([r["event"]["timestamp_utc"] for r in records],
            ["2026-01-01T00:00:00.000004+00:00",
             "2026-01-01T00:00:00.000003+00:00",
             "2026-01-01T00:00:00.000002+00:00"])

    def test_history_gets_never_advance_snapshot_or_create_events(self):
        before=self.server.controller.snapshot()
        for _ in range(4):
            self.get("/")
            self.get("/history.js")
            self.get("/api/history/events?limit=2")
        self.assertEqual(self.server.controller.snapshot(),before)
        self.assertEqual(len(self.server.controller.history_snapshots()),5)


class DefaultMemoryOnlyHistoryDashboardTest(unittest.TestCase):
    def test_live_dashboard_remains_available_when_sqlite_disabled(self):
        server=MotorPulseServer(("127.0.0.1",0),autostart=False)
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base+"/",timeout=3) as response:
                html=response.read()
                self.assertIn(b"Recorded synthetic trends",html)
            with urlopen(base+"/history.js",timeout=3) as response:
                self.assertIn(b"History is disabled.",response.read())
            with self.assertRaises(HTTPError) as error:
                urlopen(base+"/api/history/sessions?limit=100",timeout=3)
            self.assertEqual(error.exception.code,409)
            with urlopen(base+"/api/snapshot",timeout=3) as response:
                self.assertEqual(json.load(response)["tick"],1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__=="__main__":
    unittest.main()
