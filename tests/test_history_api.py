"""MP-040: localhost-only historical REST queries over MP-012 SQLite storage."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from motorpulse.__main__ import MotorPulseServer
from motorpulse.history_api import MAX_HTTP_LIMIT, HISTORY_API_VERSION, parse_query
from motorpulse.scenarios import AssetScenario, configuration_dict
from motorpulse.storage import _utc_microseconds

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def assets():
    return (
        AssetScenario("MTR-01", "Healthy"),
        AssetScenario("MTR-02", "High-load simulation", "overload", 1.0),
        AssetScenario("MTR-03", "Sensor issue", sensor_missing_onset_tick=2,
                      sensor_missing_duration_ticks=1, sensor_outlier_onset_tick=3,
                      sensor_outlier_duration_ticks=1, sensor_outlier_g=0.8),
    )


class HttpHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "api.sqlite3"
        self._start_server(database_path=self.db_path)
        self.addCleanup(self._close_server)

    def _start_server(self, **kwargs):
        self.server = MotorPulseServer(
            ("127.0.0.1", 0), autostart=False,
            assets=assets(), step_seconds=0.000001, start_time_utc=EPOCH,
            **kwargs,
        )
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def get(self, path):
        req = Request(self.base + path, method="GET")
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            payload = json.load(response)
            return response.status, payload, response.headers

    def ticks(self, n):
        for _ in range(n):
            self.server.controller.control("step")

    def session(self):
        return self.server.controller.status()["session_id"]

    def assert_ok(self, path, resource):
        code, body, headers = self.get(path)
        self.assertEqual(code, 200, body)
        self.assertEqual(body["api_version"], HISTORY_API_VERSION)
        self.assertEqual(body["source"], "synthetic")
        self.assertEqual(body["resource"], resource)
        self.assertEqual(body["page"]["count"], len(body["items"]))
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))
        return body

    def test_four_endpoints_return_versioned_bounded_envelopes(self):
        for name in ("sessions", "snapshots", "events", "alerts"):
            with self.subTest(name=name):
                report = self.assert_ok("/api/history/" + name, name)
                self.assertEqual(report["page"]["limit"], 50)
                self.assertFalse(report["page"]["has_more"])
                self.assertEqual(report["page"]["order"], "id_desc")
        self.assertEqual(len(self.get("/api/history/sessions")[1]["items"]), 1)
        self.assertEqual(len(self.get("/api/history/snapshots")[1]["items"]), 1)
        self.assertEqual(len(self.get("/api/history/events")[1]["items"]), 3)
        self.assertEqual(len(self.get("/api/history/alerts")[1]["items"]), 1)

    def test_snapshot_events_share_exact_original_telemetry_and_session(self):
        first = self.server.controller.snapshot()
        session = self.session()
        snapshots = self.assert_ok("/api/history/snapshots?session_id="+session, "snapshots")
        self.assertEqual(snapshots["items"][0]["snapshot"], first)
        self.assertEqual(snapshots["items"][0]["session_id"], session)
        events = self.assert_ok("/api/history/events?session_id="+session, "events")
        self.assertEqual({a["event"]["event_id"] for a in events["items"]},
                         {a["event_id"] for a in first["assets"]})
        self.assertEqual(events["filters"], {"session_id":session})

    def test_motor_filter_retains_sensor_quality_and_fault_metadata(self):
        self.ticks(3)
        report = self.assert_ok("/api/history/events?asset_id=MTR-03", "events")
        self.assertEqual([x["event"]["tick"] if "tick" in x["event"] else
                         int(x["event"]["event_id"].split(":")[-1]) for x in report["items"]],
                         [4,3,2,1])
        self.assertEqual({x["event"]["sensor_quality"] for x in report["items"]},
                         {"good", "missing", "outlier"})
        self.assertTrue(all(x["event"]["asset_id"] == "MTR-03" for x in report["items"]))

    def test_rule_alerts_exclude_unavailable_and_outlier(self):
        self.ticks(3)
        rows = self.assert_ok("/api/history/alerts?asset_id=MTR-02", "alerts")["items"]
        self.assertEqual([a["tick"] for a in rows], [4,3,2,1])
        self.assertTrue(all(a["severity"] == "critical" for a in rows))
        self.assertTrue(all(a["reasons"] and a["source"] == "synthetic_rule" for a in rows))
        self.assertEqual(self.get("/api/history/alerts?asset_id=MTR-03")[1]["items"], [])
        self.assertEqual(self.get("/api/history/alerts?asset_id=MTR-01")[1]["items"], [])

    def test_events_cursor_pagination_is_gapless(self):
        self.ticks(3)
        first = self.assert_ok("/api/history/events?limit=3", "events")
        self.assertTrue(first["page"]["has_more"])
        self.assertEqual(first["page"]["count"], 3)
        cursor = first["page"]["next_before_id"]
        collected = list(first["items"])
        while cursor is not None:
            page = self.assert_ok("/api/history/events?limit=3&before_id="+str(cursor), "events")
            collected.extend(page["items"])
            cursor = page["page"]["next_before_id"]
        self.assertEqual(len(collected), 12)
        ids = [x["id"] for x in collected]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(self.get("/api/history/events?limit=3&before_id=1")[1]["items"], [])

    def test_paging_remains_stable_as_newer_ticks_arrive(self):
        self.ticks(2)
        first = self.assert_ok("/api/history/snapshots?limit=1", "snapshots")
        self.ticks(2)
        next_page = self.assert_ok(
            "/api/history/snapshots?limit=2&before_id="+str(first["page"]["next_before_id"]),
            "snapshots")
        self.assertEqual([x["snapshot"]["tick"] for x in next_page["items"]],[2,1])
        self.assertFalse(next_page["page"]["has_more"])

    def test_sessions_pagination_and_filter_across_resets(self):
        previous = self.session()
        self.server.controller.control("reset")
        middle = self.session()
        self.server.controller.configure(configuration_dict(assets()))
        latest = self.session()
        self.assertEqual(len({previous,middle,latest}),3)
        first = self.assert_ok("/api/history/sessions?limit=1", "sessions")
        self.assertEqual(first["items"][0]["session_id"],latest)
        self.assertTrue(first["page"]["has_more"])
        second = self.assert_ok(
            "/api/history/sessions?limit=1&before_id="+str(first["page"]["next_before_id"]),
            "sessions")
        self.assertEqual(second["items"][0]["session_id"],middle)
        third = self.assert_ok(
            "/api/history/sessions?limit=1&before_id="+str(second["page"]["next_before_id"]),
            "sessions")
        self.assertEqual(third["items"][0]["session_id"],previous)
        self.assertFalse(third["page"]["has_more"])
        by_group=self.assert_ok("/api/history/events?session_id="+previous, "events")
        self.assertEqual(len(by_group["items"]),3)
        self.assertEqual(by_group["items"][0]["session_id"],previous)

    def test_exact_microsecond_utc_timestamp_bounds_inclusive(self):
        self.ticks(3)
        self.assertEqual(_utc_microseconds("2026-01-01T00:00:00.000001Z") + 1,
                         _utc_microseconds("2026-01-01T00:00:00.000002+00:00"))
        for name in ("snapshots","events","alerts"):
            qs = "?start_utc=2026-01-01T00%3A00%3A00.000002Z&end_utc=2026-01-01T00%3A00%3A00.000002%2B00%3A00"
            rows = self.assert_ok("/api/history/"+name+qs, name)["items"]
            expected = 3 if name=="events" else 1
            self.assertEqual(len(rows),expected,(name,rows))
            for item in rows:
                event = item.get("event")
                self.assertEqual(
                    (item.get("snapshot") or event or item).get("recorded_at_utc",
                        (item.get("snapshot") or event or item).get("timestamp_utc")),
                    "2026-01-01T00:00:00.000002+00:00")
        no = self.assert_ok(
            "/api/history/events?start_utc=2026-01-01T00%3A00%3A00.000004Z",
            "events")
        self.assertEqual(no["items"],[])

    def test_time_window_combined_with_asset_session_and_cursor(self):
        self.ticks(4)
        session=self.session()
        query=(
            "/api/history/events?asset_id=MTR-01&session_id="+session+
            "&start_utc=2026-01-01T00%3A00%3A00.000001Z"+
            "&end_utc=2026-01-01T00%3A00%3A00.000003Z&limit=1"
        )
        result=self.assert_ok(query,"events")
        self.assertEqual(result["page"]["count"],1)
        self.assertTrue(result["page"]["has_more"])
        nxt=self.assert_ok(query+"&before_id="+str(result["page"]["next_before_id"]),"events")
        self.assertEqual(len(nxt["items"]),1)
        self.assertNotEqual(result["items"][0]["id"],nxt["items"][0]["id"])
        remaining=self.assert_ok(query+"&before_id="+str(nxt["page"]["next_before_id"]),"events")
        self.assertEqual(len(remaining["items"]),1)
        self.assertFalse(remaining["page"]["has_more"])

    def test_no_sql_injection_or_unrecognized_filters(self):
        self.ticks(2)
        injection="/api/history/events?asset_id="+quote("' OR 1=1 --",safe="")
        report=self.assert_ok(injection,"events")
        self.assertEqual(report["items"],[])
        for path in (
            "/api/history/sessions?asset_id=MTR-01",
            "/api/history/snapshots?asset_id=MTR-01",
            "/api/history/alerts?severity=critical",
            "/api/history/events?raw_waveforms=1",
            "/api/history/events?sort=oldest",
        ):
            with self.subTest(path=path):
                status, body, _ = self.get(path)
                self.assertEqual(status,400)
                self.assertEqual(body["code"],"invalid_history_query")

    def test_reject_duplicate_unknown_empty_and_unpaired_parameters(self):
        for suffix in (
            "limit=3&limit=5", "limit", "asset_id=", "=hello",
            "unknown=x", "before_id=5&before_id=6",
            "start_utc=", "end_utc=%20", "limit=1&&limit=2",
        ):
            with self.subTest(suffix=suffix):
                status, body, _=self.get("/api/history/events?"+suffix)
                self.assertEqual(status,400,body)
                self.assertIn("error",body)

    def test_reject_bad_utf8_and_percent_escapes(self):
        for suffix in ("asset_id=%ZZ", "asset_id=%", "asset_id=%FF",
                       "asset_id=%F0%80%80%AF", "session_id=%GG"):
            with self.subTest(suffix=suffix):
                status, body, _=self.get("/api/history/events?"+suffix)
                self.assertEqual(status,400,body)
        long_query="asset_id="+"A"*2100
        self.assertEqual(self.get("/api/history/events?"+long_query)[0],400)

    def test_validate_limit_and_cursor_integer_bounds(self):
        for arg in (
            "limit=0", "limit=101", "limit=-1", "limit=1.5",
            "limit=01", "limit=nan", "limit=1e3", "before_id=0",
            "before_id=-3", "before_id=9223372036854775808",
            "before_id=foo",
        ):
            with self.subTest(arg=arg):
                status, body, _=self.get("/api/history/events?"+arg)
                self.assertEqual(status,400,body)
        report=self.assert_ok("/api/history/events?limit=100", "events")
        self.assertEqual(report["page"]["limit"],MAX_HTTP_LIMIT)

    def test_reject_non_utc_or_reversed_timestamp_bounds(self):
        cases=(
            "start_utc=2026-01-01T00%3A00%3A00",
            "start_utc=2026-01-01T01%3A00%3A00%2B01%3A00",
            "start_utc=2026-13-01T00%3A00%3A00Z",
            "start_utc=2026-01-01T00%3A00Z",
            "start_utc=2026-01-01T00%3A00%3A02Z&end_utc=2026-01-01T00%3A00%3A01Z",
            "end_utc=notatime",
        )
        for case in cases:
            with self.subTest(case=case):
                status,body,_=self.get("/api/history/events?"+case)
                self.assertEqual(status,400,body)

    def test_readonly_gets_do_not_advance_tick_or_insert(self):
        before=self.server.controller.snapshot()
        for _ in range(10):
            self.get("/api/history/snapshots")
            self.get("/api/history/events?limit=1")
            self.get("/api/history/alerts")
        self.assertEqual(before,self.server.controller.snapshot())
        self.assertEqual(len(self.server.controller.history_snapshots()),1)

    def test_concurrent_history_reads_and_steps(self):
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(
                lambda i: (self.server.controller.control("step"),
                           self.get("/api/history/events?limit=4")[0]), range(9)))
        self.assertTrue(all(http==200 for _,http in results))
        self.assertEqual(self.server.controller.status()["tick"],10)
        self.assertEqual(len(self.server.controller.history_snapshots()),10)
        self.assertEqual(len(self.server.controller.history_events(limit=50)),30)

    def test_reopen_file_history_visible_from_new_server(self):
        self.ticks(2)
        old_session=self.session()
        self._close_server()
        self._start_server(database_path=self.db_path)
        self.ticks(1)
        latest=self.session()
        self.assertNotEqual(latest,old_session)
        old=self.assert_ok("/api/history/snapshots?session_id="+old_session,"snapshots")
        self.assertEqual([r["snapshot"]["tick"] for r in old["items"]],[3,2,1])
        self.assertEqual([r["snapshot"]["tick"] for r in
                          self.assert_ok("/api/history/snapshots?session_id="+latest,"snapshots")["items"]],
                          [2,1])

    def test_disabled_storage_is_409_with_clear_machine_error(self):
        self._close_server()
        self._start_server()
        for name in ("sessions","snapshots","events","alerts"):
            status, body, _ = self.get("/api/history/"+name)
            self.assertEqual(status,409)
            self.assertEqual(body["code"],"history_unavailable")
            self.assertIn("--database",body["error"])
        self.assertEqual(self.get("/api/health")[0],200)

    def test_corrupt_unavailable_db_read_is_503_without_raw_path(self):
        path=str(self.db_path)
        self.server.controller._storage._db.close()
        status,body,_=self.get("/api/history/events")
        self.assertEqual(status,503,body)
        self.assertEqual(body["code"],"history_storage_error")
        self.assertNotIn(path,json.dumps(body))

    def test_unknown_api_route_is_404_not_static_fallback(self):
        status,body,_=self.get("/api/history/nope")
        self.assertEqual(status,404)
        self.assertEqual(body["error"],"Unknown API endpoint")


class QueryParserTests(unittest.TestCase):
    def test_full_schema_filter_whitelist(self):
        query=parse_query("events","session_id=abc&asset_id=MTR-01&limit=2&before_id=42")
        self.assertEqual(query, {
            "session_id":"abc", "asset_id":"MTR-01", "limit":2, "before_id":42
        })
        with self.assertRaises(ValueError):
            parse_query("sessions","start_utc=2026-01-01T00%3A00%3A00Z")
        with self.assertRaises(ValueError):
            parse_query("bogus","limit=1")


if __name__ == "__main__":
    unittest.main()
