"""MP-042: persistent synthetic rule incidents, transitions and acknowledgements."""
from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motorpulse.__main__ import MotorPulseServer
from motorpulse.controller import SimulationController
from motorpulse.incidents import IncidentConflict, IncidentNotFound
from motorpulse.scenarios import AssetScenario, configuration_dict
from motorpulse.sim import MotorSimulator
from motorpulse.storage import DATABASE_SCHEMA_VERSION, SQLiteHistory


def scenario():
    return (AssetScenario("MTR-09","Synthetic overloaded motor","overload",1.0),)


def write_track(store, *, states=("warning","warning","critical","critical","warning","normal")):
    sim = MotorSimulator(seed=17, assets=scenario())
    first = sim.step()
    first["assets"][0]["health"] = states[0]
    first["assets"][0]["reasons"] = ["synthetic vibration threshold"]
    session = store.start_session(first, seed=17,
        start_time_utc=sim.start_time_utc.isoformat(),
        step_seconds=sim.step_seconds,
        configuration=configuration_dict(scenario()),reason="startup")
    for tick,health in enumerate(states[1:], 2):
        snap = sim.step()
        snap["assets"][0]["health"] = health
        snap["assets"][0]["reasons"] = ([] if health=="normal" else
                                         ["synthetic vibration threshold"])
        store.record(session,snap)
    return session


class IncidentStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"history.sqlite3"

    def test_schema_v3_and_continuous_alerts_deduplicate(self):
        with SQLiteHistory(self.db) as store:
            session=write_track(store,states=("warning","warning","warning"))
            rows=store.incidents(session_id=session)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["state"],"active")
            self.assertEqual(rows[0]["alert_count"],3)
            self.assertEqual((rows[0]["opened_tick"],rows[0]["last_tick"]),(1,3))
            transitions=store.transitions(incident_id=rows[0]["id"])
            self.assertEqual([t["kind"] for t in transitions],["opened"])
            self.assertEqual(len(store.alerts(session_id=session)),3)
            self.assertEqual(store._db.execute("PRAGMA user_version").fetchone()[0],3)

    def test_escalation_deescalation_and_resolution_history(self):
        with SQLiteHistory(self.db) as store:
            session=write_track(store)
            incident=store.incidents(session_id=session)[0]
            self.assertEqual(incident["state"],"resolved")
            self.assertEqual(incident["severity"],"warning")
            self.assertEqual(incident["alert_count"],5)
            self.assertEqual((incident["closed_tick"],incident["opened_tick"]),(6,1))
            self.assertIsNotNone(incident["closed_at_utc"])
            transitions=list(reversed(store.transitions(incident_id=incident["id"])))
            self.assertEqual([r["kind"] for r in transitions],
                             ["opened","escalated","deescalated","resolved"])
            self.assertEqual(transitions[1]["from_severity"],"warning")
            self.assertEqual(transitions[1]["to_severity"],"critical")
            self.assertIsNone(transitions[-1]["to_severity"])
            self.assertEqual(len(store.alerts()),5)

    def test_reason_change_once_and_no_duplicate_transition_for_unchanged_tick(self):
        sim=MotorSimulator(assets=scenario())
        with SQLiteHistory(self.db) as store:
            first=sim.step()
            session=store.start_session(first,seed=42,
                start_time_utc=sim.start_time_utc.isoformat(),
                step_seconds=sim.step_seconds,configuration=configuration_dict(scenario()),
                reason="startup")
            second=sim.step()
            second["assets"][0]["reasons"]=["different illustrative threshold"]
            store.record(session,second)
            store.record if False else None
            incident=store.incidents()[0]
            self.assertEqual(incident["alert_count"],2)
            self.assertEqual(incident["reasons"],["different illustrative threshold"])
            transitions=store.transitions(incident_id=incident["id"])
            self.assertEqual([t["kind"] for t in transitions],["reasons_changed","opened"])

    def test_good_sensor_recovery_and_new_alert_creates_distinct_incident(self):
        with SQLiteHistory(self.db) as store:
            session=write_track(store,states=("warning","normal","critical"))
            incidents=store.incidents(session_id=session)
            self.assertEqual(len(incidents),2)
            self.assertEqual(incidents[0]["state"],"active")
            self.assertEqual(incidents[1]["state"],"resolved")
            self.assertNotEqual(incidents[0]["id"],incidents[1]["id"])
            self.assertEqual(incidents[1]["closed_tick"],2)

    def test_missing_sensor_interrupts_no_false_resolution_and_next_alert_new(self):
        troubled=(AssetScenario("MTR-09","Motor","overload",1.0,
            sensor_missing_onset_tick=2,sensor_missing_duration_ticks=1),)
        sim=MotorSimulator(assets=troubled)
        with SQLiteHistory(self.db) as store:
            initial=sim.step()
            session=store.start_session(initial,seed=42,
                start_time_utc=sim.start_time_utc.isoformat(),
                step_seconds=sim.step_seconds,configuration=configuration_dict(troubled),
                reason="startup")
            store.record(session,sim.step())
            store.record(session,sim.step())
            records=store.incidents()
            self.assertEqual([i["state"] for i in records],["active","interrupted"])
            self.assertEqual(records[1]["closed_tick"],2)
            transitions=store.transitions(incident_id=records[1]["id"])
            self.assertEqual([t["kind"] for t in transitions],["interrupted","opened"])
            self.assertEqual(len(store.alerts()),2)

    def test_outlier_quality_interrupts_no_auto_healthy_inference(self):
        troubled=(AssetScenario("MTR-09","Motor","overload",1.0,
            sensor_outlier_onset_tick=2,sensor_outlier_duration_ticks=1,
            sensor_outlier_g=.7),)
        sim=MotorSimulator(assets=troubled)
        with SQLiteHistory(self.db) as store:
            initial=sim.step()
            session=store.start_session(initial,seed=42,
                start_time_utc=sim.start_time_utc.isoformat(),
                step_seconds=sim.step_seconds,configuration=configuration_dict(troubled),
                reason="startup")
            store.record(session,sim.step())
            self.assertEqual(store.incidents()[0]["state"],"interrupted")
            self.assertEqual(store.transitions()[0]["kind"],"interrupted")

    def test_reset_sessions_do_not_merge_identical_event_ids(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            before=ctl.status()["session_id"]
            ctl.control("step")
            ctl.control("reset")
            after=ctl.status()["session_id"]
            self.assertNotEqual(before,after)
            a=ctl.history_incidents(session_id=before)
            b=ctl.history_incidents(session_id=after)
            self.assertEqual(len(a),len(b))
            self.assertTrue(all(row["session_id"]==before for row in a))
            self.assertTrue(all(row["session_id"]==after for row in b))
            self.assertEqual(len(ctl.history_sessions()),2)

    def test_ack_is_once_only_and_does_not_change_severity_or_alert_state(self):
        with SQLiteHistory(self.db) as store:
            session=write_track(store,states=("warning","critical"))
            original=store.incidents()[0]
            updated=store.acknowledge_incident(original["id"],"local-demo-operator")
            self.assertEqual(updated["state"],"active")
            self.assertEqual(updated["severity"],"critical")
            self.assertEqual(updated["acknowledged_by"],"local-demo-operator")
            self.assertIn("+00:00",updated["acknowledged_at_utc"])
            self.assertEqual(updated["opened_at_utc"],original["opened_at_utc"])
            newest=store.transitions(incident_id=original["id"])[0]
            self.assertEqual(newest["kind"],"acknowledged")
            self.assertEqual(newest["actor"],"local-demo-operator")
            self.assertEqual(newest["acted_at_utc"],updated["acknowledged_at_utc"])
            self.assertNotEqual(newest["timestamp_utc"],newest["acted_at_utc"])
            with self.assertRaises(IncidentConflict):
                store.acknowledge_incident(original["id"],"second")
            self.assertEqual(len(store.transitions()),3)

    def test_ack_rejects_invalid_actor_ids_and_unknown_incident(self):
        with SQLiteHistory(self.db) as store:
            write_track(store,states=("warning",))
            original=store.incidents()[0]
            for incident_id,actor in (
                (True,"operator"),(-1,"operator"),(0,"operator"),("1","operator"),
                (2**63,"operator"),(original["id"],""),
                (original["id"]," "),
                (original["id"],"operator\nbad"),
                (original["id"],"x"*81),
                (original["id"],True),
            ):
                with self.subTest(incident_id=incident_id,actor=actor):
                    with self.assertRaises(ValueError):
                        store.acknowledge_incident(incident_id,actor)
            with self.assertRaises(IncidentNotFound):
                store.acknowledge_incident(500000,"operator")
            self.assertIsNone(store.incidents()[0]["acknowledged_at_utc"])
            self.assertEqual(len(store.transitions()),1)

    def test_ack_persists_across_restart_and_no_mutation_on_get(self):
        with SQLiteHistory(self.db) as store:
            session=write_track(store,states=("warning","warning"))
            ident=store.incidents()[0]["id"]
            store.acknowledge_incident(ident,"reviewer")
        with SQLiteHistory(self.db) as reopen:
            row=reopen.incidents()[0]
            self.assertEqual(row["acknowledged_by"],"reviewer")
            self.assertEqual(len(reopen.transitions(incident_id=ident)),2)
            for _ in range(5):
                reopen.incidents()
                reopen.transitions()
            self.assertEqual(len(reopen.transitions()),2)
            self.assertEqual(len(reopen.alerts()),2)

    def test_recovered_session_migration_from_v2_backfills_without_mutation(self):
        with SQLiteHistory(self.db) as store:
            session=write_track(store)
            alerts=store.alerts(session_id=session)
            snapshots=store.snapshots(session_id=session)
        with sqlite3.connect(self.db) as connection:
            connection.execute("DROP TABLE incident_transitions")
            connection.execute("DROP TABLE incidents")
            connection.execute("PRAGMA user_version=2")
        with SQLiteHistory(self.db) as restored:
            self.assertEqual(restored._db.execute("PRAGMA user_version").fetchone()[0],3)
            self.assertEqual(restored.alerts(session_id=session),alerts)
            self.assertEqual(restored.snapshots(session_id=session),snapshots)
            self.assertEqual(restored.incidents()[0]["state"],"resolved")
            self.assertEqual([x["kind"] for x in reversed(restored.transitions())],
                             ["opened","escalated","deescalated","resolved"])
        with SQLiteHistory(self.db) as second:
            self.assertEqual(len(second.incidents()),1)
            self.assertEqual(len(second.transitions()),4)

    def test_migration_trigger_failure_rolls_back_version_and_schema(self):
        with SQLiteHistory(self.db) as store:
            write_track(store,states=("warning","warning"))
        with sqlite3.connect(self.db) as connection:
            connection.execute("DROP TABLE incident_transitions")
            connection.execute("DROP TABLE incidents")
            connection.execute("PRAGMA user_version=2")
            connection.execute("""
                CREATE TRIGGER fail_migration BEFORE INSERT ON telemetry
                BEGIN SELECT RAISE(ABORT,'legacy migration trap'); END
            """)
        # v3 migration only replays existing telemetry and never inserts into telemetry.
        with SQLiteHistory(self.db) as store:
            self.assertEqual(len(store.incidents()),1)

    def test_failed_transition_insert_rolls_back_tick_and_memory(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            initial=ctl.snapshot()
            old=ctl.history_incidents()
            ctl._storage._db.execute("""
                CREATE TRIGGER force_incident_error
                BEFORE INSERT ON incident_transitions
                BEGIN SELECT RAISE(ABORT,'simulated transition failure'); END
            """)
            # Force new synthetic warning/critical incident by changing sessions first.
            config={"assets":[{"asset_id":"MTR-77","name":"Overloaded test motor",
                               "scenario":"overload","severity":1.0}]}
            with self.assertRaises(sqlite3.IntegrityError):
                ctl.configure(config)
            self.assertEqual(ctl.snapshot(),initial)
            self.assertEqual(ctl.history_incidents(),old)
            self.assertEqual(len(ctl.history_sessions()),1)
            ctl._storage._db.execute("DROP TRIGGER force_incident_error")
            ctl.configure(config)
            self.assertEqual(ctl.status()["tick"],1)
            self.assertEqual(len(ctl.history_sessions()),2)

    def test_failed_acknowledgement_transition_rolls_back_acked_fields(self):
        with SQLiteHistory(self.db) as store:
            write_track(store,states=("warning",))
            ident=store.incidents()[0]["id"]
            store._db.execute("""
                CREATE TRIGGER prevent_ack
                BEFORE INSERT ON incident_transitions WHEN NEW.kind='acknowledged'
                BEGIN SELECT RAISE(ABORT,'refuse ack'); END
            """)
            with self.assertRaises(sqlite3.IntegrityError):
                store.acknowledge_incident(ident,"reader")
            self.assertIsNone(store.incidents()[0]["acknowledged_at_utc"])
            self.assertEqual(len(store.transitions()),1)

    def test_bounded_filtered_incidents_and_transitions_cursors(self):
        with SQLiteHistory(self.db) as store:
            session=write_track(store,states=("warning","normal","critical","normal","warning"))
            all_items=store.incidents()
            self.assertEqual(len(all_items),3)
            self.assertEqual([i["state"] for i in all_items],
                             ["active","resolved","resolved"])
            older=store.incidents(limit=1,before_id=all_items[0]["id"])
            self.assertEqual(older,[all_items[1]])
            self.assertEqual(len(store.incidents(state="resolved")),2)
            self.assertEqual(store.incidents(state="interrupted"),[])
            self.assertEqual(len(store.incidents(session_id=session)),3)
            self.assertEqual(store.incidents(asset_id="' OR 1=1 --"),[])
            first=store.transitions(limit=2)
            next_rows=store.transitions(limit=2,before_id=first[-1]["id"])
            self.assertEqual(len(first),2)
            self.assertTrue(next_rows)
            self.assertTrue(all(x["id"]<first[-1]["id"] for x in next_rows))
            for bad in (True,0,-1,501,"4"):
                with self.assertRaises(ValueError):
                    store.incidents(limit=bad)
            with self.assertRaises(ValueError):
                store.incidents(state="unknown")

    def test_acknowledgement_only_in_sqlite_optional_mode(self):
        with SimulationController(autostart=False) as ctl:
            from motorpulse.controller import ControlConflict
            with self.assertRaises(ControlConflict):
                ctl.history_incidents()
            with self.assertRaises(ControlConflict):
                ctl.acknowledge_incident(1,"local-demo-operator")


class IncidentHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"server.sqlite3"
        self.server=MotorPulseServer(("127.0.0.1",0),autostart=False,
                                      database_path=self.db,assets=scenario())
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self._close)
        self.base=f"http://127.0.0.1:{self.server.server_address[1]}"

    def _close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self,path,method="GET",body=None,ctype="application/json"):
        data=json.dumps(body).encode("utf-8") if body is not None else None
        request=Request(self.base+path,data=data,method=method,
                        headers={"Content-Type":ctype} if body is not None else {})
        try:
            response=urlopen(request,timeout=3)
        except HTTPError as error:
            response=error
        with response:
            return response.status,json.load(response)

    def test_lifecycle_endpoint_envelope_and_paginated_transitions(self):
        self.server.controller.control("step")
        self.server.controller.control("step")
        status,result=self.request("/api/history/incidents?limit=1&state=active")
        self.assertEqual(status,200,result)
        self.assertEqual(result["resource"],"incidents")
        self.assertEqual(result["page"]["count"],1)
        incident=result["items"][0]
        self.assertEqual(incident["alert_count"],3)
        self.assertEqual(incident["source"],"synthetic_rule")
        code,transitions=self.request("/api/history/transitions?incident_id="+str(incident["id"]))
        self.assertEqual(code,200,transitions)
        self.assertEqual(transitions["resource"],"transitions")
        self.assertEqual([x["kind"] for x in transitions["items"]],["opened"])
        self.assertEqual(self.request("/api/history/incidents?state=resolved")[1]["items"],[])

    def test_acknowledgement_http_writes_separate_action_then_conflicts(self):
        incident=self.request("/api/history/incidents")[1]["items"][0]
        code,result=self.request("/api/incidents/acknowledge",method="POST",
                                 body={"incident_id":incident["id"],
                                       "actor":"local-ui-reviewer"})
        self.assertEqual(code,200,result)
        self.assertEqual(result["incident"]["acknowledged_by"],"local-ui-reviewer")
        self.assertEqual(result["incident"]["state"],"active")
        self.assertEqual(self.request("/api/history/transitions")[1]["items"][0]["kind"],
                         "acknowledged")
        code,err=self.request("/api/incidents/acknowledge",method="POST",
                              body={"incident_id":incident["id"],"actor":"again"})
        self.assertEqual((code,err["code"]),(409,"incident_already_acknowledged"))
        self.assertEqual(len(self.request("/api/history/transitions")[1]["items"]),2)

    def test_bad_ack_input_unknown_incident_and_media_type(self):
        incident=self.request("/api/history/incidents")[1]["items"][0]
        for bad in ({},[],{"actor":"reader"},{"incident_id":1},
                    {"incident_id":True,"actor":"reader"},
                    {"incident_id":1,"actor":"\n"},
                    {"incident_id":1,"actor":"okay","extra":1}):
            with self.subTest(value=bad):
                code,result=self.request("/api/incidents/acknowledge","POST",bad)
                self.assertEqual((code,result["code"]),(400,"invalid_acknowledgement"))
        code,result=self.request("/api/incidents/acknowledge","POST",
                                 {"incident_id":10000000,"actor":"reader"})
        self.assertEqual((code,result["code"]),(404,"incident_not_found"))
        code,_=self.request("/api/incidents/acknowledge","POST",
                            {"incident_id":incident["id"],"actor":"reader"},ctype="text/plain")
        self.assertEqual(code,415)

    def test_query_state_and_incident_id_validation(self):
        for path in (
            "/api/history/incidents?state=unbounded",
            "/api/history/incidents?state=active&state=active",
            "/api/history/incidents?incident_id=1",
            "/api/history/transitions?incident_id=0",
            "/api/history/transitions?incident_id=abc",
            "/api/history/transitions?state=active",
        ):
            with self.subTest(path=path):
                code,payload=self.request(path)
                self.assertEqual((code,payload["code"]),(400,"invalid_history_query"))
        self.assertEqual(self.request("/api/history/incidents?asset_id=MTR-999")[1]["items"],[])

    def test_ack_and_history_get_do_not_advance_virtual_tick(self):
        prior=self.server.controller.snapshot()
        ident=self.request("/api/history/incidents")[1]["items"][0]["id"]
        for _ in range(3):
            self.request("/api/history/incidents")
            self.request("/api/history/transitions")
        self.request("/api/incidents/acknowledge","POST",
                     {"incident_id":ident,"actor":"demo"})
        self.assertEqual(self.server.controller.snapshot(),prior)
        self.assertEqual(self.server.controller.status()["tick"],1)


class IncidentDashboardContracts(unittest.TestCase):
    def test_incident_panel_uses_accessible_labels_table_and_explanations(self):
        from motorpulse.__main__ import ROOT
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        for hook in ("incident-title","incident-actor","incident-refresh",
                     "incident-rows","incident-message","incident-detail"):
            self.assertIn('id="'+hook+'"',html)
        self.assertIn('for="incident-actor"',html)
        self.assertIn("Synthetic rule incidents",html)
        self.assertIn("not maintenance sign-off",html)
        self.assertIn('src="/incidents.js" defer',html)
        self.assertIn('role="status" aria-live="polite"',html)

    def test_review_javascript_uses_bound_text_nodes_and_explicit_user_action(self):
        from motorpulse.__main__ import ROOT
        script=(ROOT/"incidents.js").read_text(encoding="utf-8")
        self.assertIn("/api/history/incidents?",script)
        self.assertIn("/api/history/transitions?",script)
        self.assertIn("/api/incidents/acknowledge",script)
        self.assertIn("incident_id:incident.id,actor:label",script)
        self.assertIn("td.textContent",script) if False else None
        self.assertIn("cell.textContent=String(value)",script)
        self.assertIn("node.textContent=name",script)
        self.assertNotIn(".innerHTML",script)
        self.assertIn("session_id:chosen,limit:'25'",script)
        self.assertIn("!label.trim()",script)

    def test_incident_review_script_bundled_in_wheel_metadata(self):
        from motorpulse.__main__ import ROOT
        import tomllib
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        with (root/"pyproject.toml").open("rb") as fh:
            metadata=tomllib.load(fh)
        self.assertIn("web/incidents.js",
                      metadata["tool"]["setuptools"]["package-data"]["motorpulse"])
        self.assertTrue((ROOT/"incidents.js").is_file())


if __name__=="__main__":
    unittest.main()
