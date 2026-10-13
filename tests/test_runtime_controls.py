"""MP-041: safe runtime seed/timing changes and accessible dashboard controls."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import json
import math
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motorpulse.__main__ import MotorPulseServer, ROOT
from motorpulse.controller import ControlConflict, SimulationController
from motorpulse.scenarios import DEFAULT_ASSETS, configuration_dict
from motorpulse.sim import MotorSimulator

REPOSITORY = Path(__file__).resolve().parents[1]


class RuntimeControllerTests(unittest.TestCase):
    def test_change_seed_and_virtual_step_is_deterministic(self):
        original_time=datetime(2030, 2, 3, tzinfo=timezone.utc)
        with SimulationController(seed=9,autostart=False,start_time_utc=original_time) as ctl:
            first=ctl.snapshot()
            ctl.control("step")
            result=ctl.configure_runtime({
                "seed":90,"step_seconds":0.25,"interval_seconds":0.15,
            })
            self.assertEqual(result["seed"],90)
            self.assertEqual(result["tick"],1)
            self.assertEqual(result["state"],"paused")
            self.assertEqual(result["interval_seconds"],0.15)
            self.assertEqual(result["step_seconds"],0.25)
            self.assertEqual(result["start_time_utc"],original_time.isoformat())
            self.assertEqual(ctl.snapshot(),MotorSimulator(
                seed=90,start_time_utc=original_time,step_seconds=.25,
                assets=DEFAULT_ASSETS,
            ).step())
            self.assertNotEqual(first,ctl.snapshot())
            ctl.control("step")
            second=ctl.snapshot()
            self.assertEqual(second["recorded_at_utc"],"2030-02-03T00:00:00.250000+00:00")
            ctl.control("reset")
            ctl.control("step")
            self.assertEqual(ctl.snapshot(),second)
            self.assertEqual(ctl.status()["seed"],90)

    def test_reject_nonfinite_boolean_unknown_wrong_shapes(self):
        with SimulationController(autostart=False) as ctl:
            baseline=ctl.snapshot()
            state=ctl.status()
            good={"seed":2,"step_seconds":0.125,"interval_seconds":.15}
            for invalid in (
                {},None,[],{"seed":2},
                {**good,"extra":4},
                {**good,"seed":True},{**good,"seed":-1},
                {**good,"seed":2_147_483_648},{**good,"seed":2.5},
                {**good,"seed":"3"},{**good,"step_seconds":True},
                {**good,"step_seconds":math.nan},
                {**good,"step_seconds":math.inf},
                {**good,"step_seconds":0},
                {**good,"step_seconds":0.0000001},
                {**good,"step_seconds":86401},
                {**good,"interval_seconds":True},
                {**good,"interval_seconds":.049},
                {**good,"interval_seconds":3601},
                {**good,"interval_seconds":math.nan},
                {**good,"interval_seconds":"1.5"},
            ):
                with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                    ctl.configure_runtime(invalid)
                self.assertEqual(ctl.snapshot(),baseline)
                self.assertEqual(ctl.status(),state)

    def test_reject_submicrosecond_step_precision(self):
        with SimulationController(autostart=False) as ctl:
            with self.assertRaisesRegex(ValueError,"microseconds"):
                ctl.configure_runtime({
                    "seed":3,"step_seconds":.0000015,"interval_seconds":.5,
                })
            self.assertEqual(ctl.status()["step_seconds"],1.5)

    def test_new_setting_can_pause_background_worker(self):
        with SimulationController(seed=10,autostart=False,interval_seconds=.03) as ctl:
            ctl.control("start")
            cutoff=time.monotonic()+1
            while ctl.status()["tick"]<2 and time.monotonic()<cutoff:
                time.sleep(.005)
            self.assertGreaterEqual(ctl.status()["tick"],2)
            result=ctl.configure_runtime({
                "seed":11,"interval_seconds":.2,"step_seconds":2,
            })
            self.assertEqual(result["state"],"paused")
            self.assertEqual(result["tick"],1)
            time.sleep(.07)
            self.assertEqual(ctl.status()["tick"],1)

    def test_configure_runtime_preserves_asset_fault_settings(self):
        with SimulationController(autostart=False) as ctl:
            assets=configuration_dict(DEFAULT_ASSETS)
            ctl.configure_runtime({
                "seed":777, "step_seconds":3, "interval_seconds":1,
            })
            self.assertEqual(ctl.configuration(),assets)
            self.assertEqual(ctl._sim.assets,DEFAULT_ASSETS)
            self.assertEqual(ctl.status()["tick"],1)

    def test_sqlite_runtime_update_preserves_old_sessions(self):
        with TemporaryDirectory() as temp:
            db=Path(temp)/"runtime.sqlite3"
            with SimulationController(autostart=False,seed=1,database_path=db) as ctl:
                old=ctl.status()["session_id"]
                ctl.control("step")
                before=ctl.history_snapshots(session_id=old)
                ctl.configure_runtime({
                    "seed":99,"step_seconds":.000002,"interval_seconds":.5,
                })
                new=ctl.status()["session_id"]
                self.assertNotEqual(old,new)
                self.assertEqual([x["snapshot"] for x in ctl.history_snapshots(session_id=old)],
                                 [x["snapshot"] for x in before])
                self.assertEqual(len(ctl.history_sessions()),2)
                self.assertEqual(ctl.history_sessions()[0]["seed"],99)
                self.assertEqual(ctl.history_sessions()[0]["step_seconds"],.000002)
                self.assertEqual(ctl.history_sessions()[0]["reason"],"configure")
                self.assertEqual(len(ctl.history_snapshots(session_id=new)),1)

    def test_sqlite_trigger_failure_is_fully_atomic(self):
        with TemporaryDirectory() as temp:
            with SimulationController(autostart=False,database_path=Path(temp)/"runtime.db") as ctl:
                prev=ctl.status()
                snap=ctl.snapshot()
                old_cfg=ctl.configuration()
                ctl._storage._db.execute("""
                    CREATE TRIGGER mp041_forced_failure BEFORE INSERT ON sessions
                    BEGIN SELECT RAISE(ABORT, 'synthetic injected failure'); END
                """)
                with self.assertRaises(sqlite3.IntegrityError):
                    ctl.configure_runtime({
                        "seed":102,"step_seconds":.25,"interval_seconds":.5,
                    })
                self.assertEqual(ctl.status(),prev)
                self.assertEqual(ctl.snapshot(),snap)
                self.assertEqual(ctl.configuration(),old_cfg)
                self.assertEqual(len(ctl.history_sessions()),1)
                ctl._storage._db.execute("DROP TRIGGER mp041_forced_failure")
                ctl.configure_runtime({
                    "seed":102,"step_seconds":.25,"interval_seconds":.5,
                })
                self.assertNotEqual(ctl.status()["session_id"],prev["session_id"])

    def test_closed_controller_rejects_runtime_updates(self):
        ctl=SimulationController(autostart=False)
        ctl.close()
        with self.assertRaises(ControlConflict):
            ctl.configure_runtime({
                "seed":12,"interval_seconds":1,"step_seconds":1,
            })


class RuntimeHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=MotorPulseServer(("127.0.0.1",0),autostart=False)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.origin=f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.server.controller.configure_runtime({
            "seed":42,"interval_seconds":1.5,"step_seconds":1.5,
        })

    def request(self,method,path,body=None,ctype="application/json"):
        data=json.dumps(body).encode("utf-8") if body is not None else None
        req=Request(self.origin+path,data=data,method=method,
                    headers={"Content-Type":ctype} if data is not None else {})
        try:
            response=urlopen(req,timeout=3)
        except HTTPError as exc:
            response=exc
        with response:
            return response.status,json.load(response)

    def test_put_runtime_updates_live_status_and_snapshots(self):
        code,result=self.request("PUT","/api/runtime",{
            "seed":47,"step_seconds":0.5,"interval_seconds":0.25,
        })
        self.assertEqual(code,200,result)
        self.assertEqual(result["seed"],47)
        self.assertEqual(result["tick"],1)
        self.assertEqual(self.request("GET","/api/status")[1],result)
        self.assertEqual(self.request("GET","/api/snapshot")[1],
                         MotorSimulator(seed=47,step_seconds=.5).step())
        self.assertEqual(self.request("POST","/api/control",{"action":"step"})[1]["tick"],2)
        self.assertEqual(self.request("GET","/api/snapshot")[1]["recorded_at_utc"],
                         "2026-01-01T00:00:00.500000+00:00")

    def test_bad_runtime_payload_returns_400_without_state_change(self):
        before=self.request("GET","/api/snapshot")[1]
        status=self.request("GET","/api/status")[1]
        for value in ({"seed":True,"step_seconds":1,"interval_seconds":1},
                      {"seed":11,"step_seconds":-1,"interval_seconds":1},
                      {"seed":5,"step_seconds":1,"interval_seconds":"slow"},
                      {"seed":5,"step_seconds":1},
                      {"seed":5,"step_seconds":1,"interval_seconds":1,"other":0},
                      {"seed":1.5,"step_seconds":1,"interval_seconds":1}):
            with self.subTest(value=value):
                code,result=self.request("PUT","/api/runtime",value)
                self.assertEqual(code,400,result)
                self.assertIn("error",result)
                self.assertEqual(self.request("GET","/api/snapshot")[1],before)
                self.assertEqual(self.request("GET","/api/status")[1],status)

    def test_runtime_wrong_method_and_content_type(self):
        self.assertEqual(self.request("GET","/api/runtime")[0],404)
        self.assertEqual(self.request("POST","/api/runtime",{"seed":1})[0],404)
        self.assertEqual(self.request("PUT","/api/runtime",{
            "seed":1,"interval_seconds":1,"step_seconds":1,
        },ctype="text/plain")[0],415)
        self.assertEqual(self.request("GET","/api/status")[1]["seed"],42)


class RuntimeDashboardTests(unittest.TestCase):
    class Fields(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids=set()
            self.labels=set()
            self.inputs={}
            self.buttons=set()
        def handle_starttag(self,tag,attrs):
            props=dict(attrs)
            if "id" in props:
                self.ids.add(props["id"])
            if tag=="label" and "for" in props:
                self.labels.add(props["for"])
            if tag=="input" and "id" in props:
                self.inputs[props["id"]]=props
            if tag=="button" and "data-action" in props:
                self.buttons.add(props["data-action"])

    def test_packaged_html_has_accessible_seed_virtual_and_wall_time_fields(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        parser=self.Fields()
        parser.feed(html)
        for field in ("runtime-seed","runtime-step","runtime-interval"):
            self.assertIn(field,parser.ids)
            self.assertIn(field,parser.labels)
            self.assertEqual(parser.inputs[field]["required"],None)
            self.assertEqual(parser.inputs[field]["type"],"number")
        self.assertEqual(parser.buttons,{"start","pause","step","reset"})
        self.assertIn("role=\"status\" aria-live=\"polite\"",html)
        self.assertIn("id=\"runtime-active\"",html)
        self.assertIn("id=\"runtime-message\"",html)
        self.assertIn("id=\"apply-scenarios\"",html)

    def test_html_uses_runtime_endpoint_and_reports_edit_failure(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/runtime'",html)
        self.assertIn("runtimeForm.reportValidity()",html)
        self.assertIn("runtimeLoaded",html)
        self.assertIn("runtimeMessage.classList.add('error')",html)
        self.assertIn("runtimeApply.disabled=busy",html)
        self.assertIn("simulated UTC",html)
        self.assertIn("real update interval",html)
        self.assertIn("No physical motor clock",html)
        self.assertIn("@media(max-width:650px)",html)


if __name__ == "__main__":
    unittest.main()
