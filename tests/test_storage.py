"""MP-012: SQLite snapshot/alert history, migrations and controller recovery."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from urllib.request import Request, urlopen

from motorpulse.__main__ import MotorPulseServer
from motorpulse.controller import ControlConflict, SimulationController
from motorpulse.scenarios import AssetScenario, configuration_dict
from motorpulse.sim import MotorSimulator
from motorpulse.storage import DATABASE_SCHEMA_VERSION, MAX_PAGE_SIZE, SQLiteHistory


def motor(name="MTR-A1", scenario="healthy", **options):
    return AssetScenario(name, name, scenario, **options)


class SQLiteHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "monitor.sqlite3"

    def test_new_database_schema_foreign_keys_and_indexes(self):
        with SQLiteHistory(self.db) as history:
            self.assertEqual(history._db.execute("PRAGMA user_version").fetchone()[0],
                             DATABASE_SCHEMA_VERSION)
            self.assertEqual(history._db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual({r[0] for r in history._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")},
                {"sessions", "snapshots", "telemetry", "rule_alerts", "sqlite_sequence"})
            self.assertTrue(any("session" in r[1] for r in history._db.execute(
                "PRAGMA index_list(telemetry)")))
        self.assertTrue(self.db.is_file())

    def test_snapshot_and_event_json_round_trip(self):
        with SimulationController(autostart=False, database_path=self.db) as ctl:
            session = ctl.status()["session_id"]
            snap = ctl.snapshot()
            self.assertEqual(ctl.history_snapshots(session_id=session)[0]["snapshot"], snap)
            self.assertEqual(len(ctl.history_events(session_id=session)),len(snap["assets"]))
            self.assertEqual(
                {row["event"]["event_id"] for row in ctl.history_events()},
                {a["event_id"] for a in snap["assets"]}
            )
            self.assertEqual(ctl.history_sessions()[0]["reason"],"startup")
            self.assertEqual(ctl.status()["storage"],"ok")

    def test_persistence_retains_old_sessions_across_controller_restart(self):
        with SimulationController(seed=7,autostart=False,database_path=self.db) as first:
            session1=first.status()["session_id"]
            original=first.snapshot()
            first.control("step")
            first.control("step")
            before=first.history_snapshots(session_id=session1)
            self.assertEqual([x["snapshot"]["tick"] for x in before],[3,2,1])
        with SimulationController(seed=7,autostart=False,database_path=self.db) as second:
            session2=second.status()["session_id"]
            self.assertNotEqual(session1,session2)
            self.assertEqual(second.snapshot(),original)
            self.assertEqual(second.status()["tick"],1)
            self.assertEqual(
                [x["snapshot"] for x in second.history_snapshots(session_id=session1)], 
                [x["snapshot"] for x in before]
            )
            self.assertEqual([x["snapshot"]["tick"] for x in
                              second.history_snapshots(session_id=session2)],[1])
            self.assertEqual(len(second.history_sessions()),2)
            # Original deterministic event IDs repeat, but session-scoped uniqueness does not collide.
            previous={r["event"]["event_id"] for r in second.history_events(session_id=session1)}
            fresh={r["event"]["event_id"] for r in second.history_events(session_id=session2)}
            self.assertTrue(fresh.issubset(previous))

    def test_reset_and_configure_open_distinct_sessions_without_history_loss(self):
        with SimulationController(seed=45,autostart=False,database_path=self.db) as ctl:
            baseline=ctl.snapshot()
            first=ctl.status()["session_id"]
            ctl.control("step")
            ctl.control("reset")
            second=ctl.status()["session_id"]
            self.assertNotEqual(first,second)
            self.assertEqual(ctl.snapshot(),baseline)
            cfg=configuration_dict((motor("MTR-XY", "overload", severity=1.0),))
            ctl.configure(cfg)
            third=ctl.status()["session_id"]
            self.assertNotIn(third,(first,second))
            self.assertEqual(ctl.snapshot()["assets"][0]["asset_id"],"MTR-XY")
            self.assertEqual([x["reason"] for x in ctl.history_sessions()],
                             ["configure","reset","startup"])
            self.assertEqual([len(ctl.history_snapshots(session_id=s)) 
                              for s in (first,second,third)],[2,1,1])
            self.assertEqual(ctl.history_sessions()[0]["configuration"],cfg)

    def test_warning_critical_alerts_only_when_sensor_good(self):
        hot=motor("MTR-HOT","overload",severity=1.0, onset_tick=1,
                  sensor_missing_onset_tick=2,sensor_missing_duration_ticks=1,
                  sensor_outlier_onset_tick=3,sensor_outlier_duration_ticks=1,
                  sensor_outlier_g=1.0)
        with SimulationController(assets=(hot,),autostart=False,database_path=self.db) as ctl:
            ctl.control("step")
            ctl.control("step")
            ctl.control("step")
            alerts=ctl.history_alerts()
            self.assertEqual([a["tick"] for a in alerts],[4,1])
            self.assertTrue(all(a["severity"]=="critical" for a in alerts))
            self.assertTrue(all(a["source"]=="synthetic_rule" for a in alerts))
            self.assertTrue(all(a["reasons"] for a in alerts))
            events=ctl.history_events()
            self.assertEqual(len(events),4)
            self.assertEqual({e["event"]["health"] for e in events},
                             {"critical","suspect","unavailable"})
            self.assertEqual(len(ctl.history_alerts(asset_id="MTR-NOPE")),0)

    def test_duplicate_snapshot_and_event_identifiers_roll_back(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            session=ctl.status()["session_id"]
            with self.assertRaises(sqlite3.IntegrityError):
                ctl._storage.record(session,ctl.snapshot())
            self.assertEqual(len(ctl.history_snapshots()),1)
            self.assertEqual(len(ctl.history_events()),len(ctl.snapshot()["assets"]))
            with self.assertRaises(sqlite3.IntegrityError):
                ctl._storage.record("nonexistent-session", {
                    **ctl.snapshot(), "tick": 3,
                })
            self.assertEqual(len(ctl.history_snapshots()),1)

    def test_failed_step_preserves_memory_and_durable_history(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            first=ctl.snapshot()
            ctl._storage._db.execute("""
                CREATE TRIGGER reject_new_motor_event
                BEFORE INSERT ON telemetry
                BEGIN SELECT RAISE(ABORT, 'forced storage failure'); END
            """)
            with self.assertRaises(sqlite3.IntegrityError):
                ctl.control("step")
            self.assertEqual(ctl.snapshot(),first)
            self.assertEqual(ctl.status()["tick"],1)
            self.assertEqual(len(ctl.history_snapshots()),1)
            self.assertEqual(len(ctl.history_events()),len(first["assets"]))
            ctl._storage._db.execute("DROP TRIGGER reject_new_motor_event")
            self.assertEqual(ctl.control("step")["tick"],2)
            self.assertEqual(len(ctl.history_snapshots()),2)

    def test_failed_reset_or_configure_keeps_old_session_and_settings(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            old_status=ctl.status()
            old_snapshot=ctl.snapshot()
            ctl._storage._db.execute("""
                CREATE TRIGGER reject_new_session BEFORE INSERT ON sessions
                BEGIN SELECT RAISE(ABORT, 'reject session'); END
            """)
            with self.assertRaises(sqlite3.IntegrityError):
                ctl.control("reset")
            with self.assertRaises(sqlite3.IntegrityError):
                ctl.configure(configuration_dict((motor("MTR-XX"),)))
            self.assertEqual(ctl.status(),old_status)
            self.assertEqual(ctl.snapshot(),old_snapshot)
            self.assertEqual(len(ctl.history_sessions()),1)

    def test_background_worker_pauses_and_marks_storage_failure(self):
        with SimulationController(autostart=False,interval_seconds=.005,
                                  database_path=self.db) as ctl:
            ctl._storage._db.execute("""
                CREATE TRIGGER reject_step BEFORE INSERT ON snapshots
                WHEN NEW.tick > 1
                BEGIN SELECT RAISE(ABORT, 'forced background storage fault'); END
            """)
            ctl.control("start")
            deadline=time.monotonic()+1
            while ctl.status()["storage"]!="error" and time.monotonic()<deadline:
                time.sleep(.005)
            self.assertEqual(ctl.status()["storage"],"error")
            self.assertEqual(ctl.status()["state"],"paused")
            self.assertEqual(ctl.status()["tick"],1)
            self.assertEqual(len(ctl.history_snapshots()),1)
            with self.assertRaises(ControlConflict):
                ctl.control("start")

    def test_parameterized_queries_pagination_filters_and_validation(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            ctl.control("step")
            ctl.control("step")
            all_events=ctl.history_events(limit=MAX_PAGE_SIZE)
            self.assertEqual(len(all_events),9)
            ids=[r["id"] for r in all_events]
            self.assertEqual(ids,sorted(ids,reverse=True))
            next_page=ctl.history_events(limit=2,before_id=ids[1])
            self.assertEqual(next_page,[all_events[2],all_events[3]])
            filtered=ctl.history_events(asset_id="MTR-01")
            self.assertTrue(all(x["event"]["asset_id"]=="MTR-01" for x in filtered))
            injection=ctl.history_events(asset_id="' OR 1=1 --")
            self.assertEqual(injection,[])
            for invalid in (0,MAX_PAGE_SIZE+1,-1,True,"10"):
                with self.subTest(limit=invalid),self.assertRaises(ValueError):
                    ctl.history_events(limit=invalid)
            for bad in (0,-1,True,"4"):
                with self.subTest(cursor=bad),self.assertRaises(ValueError):
                    ctl.history_snapshots(before_id=bad)

    def test_read_only_snapshot_does_not_persist_new_rows(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            baseline=ctl.snapshot()
            for _ in range(15):
                self.assertEqual(ctl.snapshot(),baseline)
                ctl.status()
            self.assertEqual(len(ctl.history_snapshots()),1)

    def test_no_database_mode_preserves_existing_behavior_and_no_file(self):
        with SimulationController(autostart=False) as ctl:
            self.assertNotIn("storage",ctl.status())
            self.assertNotIn("session_id",ctl.status())
            ctl.control("step")
            with self.assertRaises(ControlConflict):
                ctl.history_events()
        self.assertFalse(self.db.exists())

    def test_reject_symlinked_path_and_missing_parent(self):
        real=self.root/"real.sqlite3"
        with SQLiteHistory(real):
            pass
        alias=self.root/"alias.sqlite3"
        alias.symlink_to(real)
        with self.assertRaisesRegex(ValueError,"symlink"):
            SQLiteHistory(alias)
        with self.assertRaises(ValueError):
            SQLiteHistory(self.root/"missing"/"no.sqlite3")
        with self.assertRaises(ValueError):
            SQLiteHistory(":memory:")

    def test_database_future_version_or_unknown_tables_fails_closed(self):
        with sqlite3.connect(self.db) as db:
            db.execute("PRAGMA user_version=9")
        with self.assertRaisesRegex(ValueError,"future schema"):
            SQLiteHistory(self.db)
        with sqlite3.connect(self.db) as db:
            db.execute("PRAGMA user_version=0")
            db.execute("CREATE TABLE unrelated_records(id INTEGER)")
        with self.assertRaisesRegex(ValueError,"unrecognized"):
            SQLiteHistory(self.db)

    def test_upgrade_v1_to_v2_keeps_historical_telemetry(self):
        with SimulationController(autostart=False,database_path=self.db) as ctl:
            original=ctl.snapshot()
            current_id=ctl.status()["session_id"]
        with sqlite3.connect(self.db) as db:
            db.execute("DROP TABLE rule_alerts")
            for name in ("idx_snapshots_session","idx_telemetry_session_asset",
                         "idx_alerts_session_asset"):
                db.execute(f"DROP INDEX IF EXISTS {name}")
            db.execute("PRAGMA user_version=1")
        with SQLiteHistory(self.db) as restored:
            self.assertEqual(restored._db.execute("PRAGMA user_version").fetchone()[0],2)
            self.assertEqual(restored.snapshots(session_id=current_id)[0]["snapshot"],
                             original)
            self.assertEqual(len(restored.events(session_id=current_id)),len(original["assets"]))
            self.assertEqual(restored.alerts(),[])
            sim=MotorSimulator(assets=(motor("MTR-HOT","overload",severity=1.0),))
            another=restored.start_session(
                sim.step(),seed=42,start_time_utc=sim.start_time_utc.isoformat(),
                step_seconds=sim.step_seconds,configuration={"assets":[]},reason="startup")
            self.assertEqual(len(restored.alerts(session_id=another)),1)

    def test_fresh_open_against_corrupt_non_database_file_rejected(self):
        self.db.write_bytes(b"not-a-sqlite-database")
        with self.assertRaises(sqlite3.DatabaseError):
            SQLiteHistory(self.db)

    def test_concurrent_background_steps_and_history_reads(self):
        with SimulationController(autostart=False,interval_seconds=.01,
                                  database_path=self.db) as ctl:
            ctl.control("start")
            deadline=time.monotonic()+1.5
            while ctl.status()["tick"]<4 and time.monotonic()<deadline:
                ctl.history_events(limit=5)
                time.sleep(.003)
            ctl.control("pause")
            tick=ctl.status()["tick"]
            self.assertGreaterEqual(tick,4)
            self.assertEqual(len(ctl.history_snapshots()),tick)
            self.assertEqual(len(ctl.history_events(limit=500)),tick*3)

    def test_closed_connection_rejects_new_history_and_writes(self):
        store=SQLiteHistory(self.db)
        store.close()
        self.assertFalse(store._closed is False)
        with self.assertRaises(ValueError):
            store.snapshots()
        with self.assertRaises(ValueError):
            store.record("closed",MotorSimulator().step())


class SQLiteHttpTests(unittest.TestCase):
    def test_server_database_opt_in_http_step_and_restart(self):
        with TemporaryDirectory() as temporary:
            db=Path(temporary)/"server.sqlite3"
            server=MotorPulseServer(("127.0.0.1",0),autostart=False,database_path=db)
            host=f"http://127.0.0.1:{server.server_address[1]}"
            t=threading.Thread(target=server.serve_forever,daemon=True)
            t.start()
            try:
                def get(path):
                    with urlopen(host+path,timeout=3) as resp:
                        return json.load(resp)
                first=get("/api/snapshot")
                status=get("/api/status")
                self.assertEqual(status["storage"],"ok")
                session=status["session_id"]
                with urlopen(Request(host+"/api/control",
                                     data=json.dumps({"action":"step"}).encode(),
                                     headers={"Content-Type":"application/json"},
                                     method="POST"),timeout=3) as resp:
                    self.assertEqual(json.load(resp)["tick"],2)
                self.assertEqual(get("/api/snapshot")["tick"],2)
                self.assertEqual(len(server.controller.history_snapshots(session_id=session)),2)
                self.assertEqual(server.controller.history_snapshots(session_id=session)[-1]["snapshot"],first)
            finally:
                server.shutdown()
                server.server_close()
                t.join(timeout=3)
            with SQLiteHistory(db) as store:
                self.assertEqual(len(store.sessions()),1)
                self.assertEqual(len(store.snapshots()),2)


if __name__ == "__main__":
    unittest.main()
