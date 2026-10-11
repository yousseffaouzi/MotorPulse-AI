"""MP-021: end-to-end localhost HTTP contracts and deterministic replay.

Standard-library only. Uses an ephemeral loopback port; never reaches the Internet.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.client import HTTPConnection
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motorpulse.__main__ import MAX_CONTROL_BODY_BYTES, MotorPulseServer
from motorpulse.schema import SCHEMA_VERSION, validate_snapshot
from motorpulse.scenarios import DEFAULT_ASSETS, AssetScenario, configuration_dict, parse_configuration
from motorpulse.sim import MotorSimulator

ROOT = Path(__file__).resolve().parents[1]


class DashboardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.actions = set()
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if props.get("id"):
            self.ids.add(props["id"])
        if tag == "button" and props.get("data-action"):
            self.actions.add(props["data-action"])
        if tag == "script":
            self.scripts += 1


class LocalApiContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MotorPulseServer(("127.0.0.1", 0), autostart=False)
        cls.port = cls.server.server_address[1]
        cls.url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        assert not cls.thread.is_alive(), "HTTP server shutdown should complete"

    def setUp(self):
        self.server.controller.configure(configuration_dict(DEFAULT_ASSETS))

    def request(self, path, method="GET", body=None, content_type="application/json"):
        headers = {"Content-Type": content_type} if body is not None else {}
        data = body if isinstance(body, bytes) else (
            json.dumps(body).encode("utf-8") if body is not None else None
        )
        request = Request(self.url + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            payload = (json.loads(raw)
                       if "application/json" in response.headers.get("Content-Type", "")
                       else raw)
            if path.startswith("/api/"):
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            return response.status, payload, response.headers

    def raw_request(self, method, path, body=b"", headers=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.putrequest(method, path)
            for key, value in (headers or {}).items():
                conn.putheader(key, value)
            conn.endheaders(body)
            result = conn.getresponse()
            return result.status, json.loads(result.read()), dict(result.getheaders())
        finally:
            conn.close()

    def test_health_status_config_and_response_headers(self):
        code, health, headers = self.request("/api/health")
        self.assertEqual(code, 200)
        self.assertEqual(health, {"status": "ok", "source": "simulation"})
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("application/json", headers["Content-Type"])
        code, status, _ = self.request("/api/status")
        self.assertEqual(code, 200)
        self.assertEqual(status["state"], "paused")
        self.assertEqual(status["tick"], 1)
        self.assertIn("start_time_utc", status)
        self.assertIn("simulated_at_utc", status)
        self.assertEqual(self.request("/api/config")[1], configuration_dict(DEFAULT_ASSETS))

    def test_snapshot_shape_units_and_timestamp_consistency(self):
        code, snapshot, _ = self.request("/api/snapshot")
        self.assertEqual(code, 200)
        validate_snapshot(snapshot)
        self.assertEqual(snapshot["schema_version"], SCHEMA_VERSION)
        self.assertEqual(snapshot["source"], "synthetic")
        self.assertEqual(snapshot["tick"], 1)
        self.assertEqual(len({a["event_id"] for a in snapshot["assets"]}), 3)
        for asset in snapshot["assets"]:
            self.assertEqual(asset["timestamp_utc"], snapshot["recorded_at_utc"])
            self.assertAlmostEqual(asset["shaft_frequency_hz"], asset["rpm"] / 60, places=3)
            self.assertAlmostEqual(asset["window_duration_s"],
                                   asset["sample_count"] / asset["sample_rate_hz"])
            self.assertIn(asset["progression"], ("constant", "linear", "exponential"))
            self.assertIn(asset["fault_phase"],
                          ("healthy", "scheduled", "ramping", "steady", "ended"))
        self.assertEqual(json.loads(json.dumps(snapshot)), snapshot)

    def test_get_snapshot_never_advances(self):
        original = self.request("/api/snapshot")[1]
        for _ in range(8):
            self.assertEqual(self.request("/api/snapshot?cache=off")[1], original)
            self.assertEqual(self.request("/api/status")[1]["tick"], 1)
        self.assertEqual(self.request("/api/control", "POST", {"action": "step"})[1]["tick"], 2)
        self.assertEqual(self.request("/api/snapshot")[1]["tick"], 2)

    def test_parallel_reads_and_parallel_steps(self):
        original = self.request("/api/snapshot")[1]
        with ThreadPoolExecutor(max_workers=6) as pool:
            snapshots = list(pool.map(lambda _: self.request("/api/snapshot")[1],
                                      range(30)))
        self.assertTrue(all(x == original for x in snapshots))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(
                lambda _: self.request("/api/control", "POST", {"action": "step"}),
                range(16)))
        self.assertTrue(all(code == 200 for code, _, _ in results))
        self.assertEqual(sorted(payload["tick"] for _, payload, _ in results),
                         list(range(2, 18)))
        self.assertEqual(self.request("/api/snapshot")[1]["tick"], 17)

    def test_control_start_pause_step_reset_and_conflict(self):
        self.assertEqual(self.request("/api/control", "POST", {"action": "start"})[1]["state"],
                         "running")
        code, error, _ = self.request("/api/control", "POST", {"action": "step"})
        self.assertEqual(code, 409)
        self.assertIn("error", error)
        self.assertEqual(self.request("/api/control", "POST", {"action": "pause"})[1]["state"],
                         "paused")
        self.assertEqual(self.request("/api/control", "POST", {"action": "step"})[1]["tick"], 2)
        reset = self.request("/api/control", "POST", {"action": "reset"})[1]
        self.assertEqual(reset["tick"], 1)
        self.assertEqual(reset["state"], "paused")

    def test_unknown_routes_and_wrong_endpoint_methods(self):
        for method, path, body in (
            ("GET", "/api/not-found", None),
            ("POST", "/api/status", {"action": "step"}),
            ("PUT", "/api/snapshot", {"assets": []}),
        ):
            with self.subTest(method=method, path=path):
                code, error, headers = self.request(path, method, body)
                self.assertEqual(code, 404)
                self.assertIn("error", error)
                self.assertIn("application/json", headers["Content-Type"])

    def test_invalid_json_and_bad_controls_are_non_mutating(self):
        first = self.request("/api/snapshot")[1]
        for raw in (b"{bad", b"[]", b"null", b"123", b'"text"', b"\xff"):
            with self.subTest(raw=raw):
                code, error, _ = self.request("/api/control", "POST", raw)
                self.assertEqual(code, 400)
                self.assertIn("error", error)
        for payload in ({}, {"action": None}, {"action": True},
                        {"action": "unknown"}, {"action": "pause", "extra": 1}):
            with self.subTest(payload=payload):
                code, error, _ = self.request("/api/control", "POST", payload)
                self.assertEqual(code, 400)
                self.assertIn("error", error)
        self.assertEqual(self.request("/api/snapshot")[1], first)

    def test_content_types_content_lengths_and_body_limit(self):
        first = self.request("/api/snapshot")[1]
        for method, path, body in (
            ("POST", "/api/control", {"action": "step"}),
            ("PUT", "/api/config", {"assets": []}),
        ):
            for mime in ("text/plain", "application/x-www-form-urlencoded",
                         "application/xml"):
                with self.subTest(method=method, mime=mime):
                    code, error, _ = self.request(path, method, body, mime)
                    self.assertEqual(code, 415)
                    self.assertIn("error", error)
        for length, status in (
            ("0", 413), (str(MAX_CONTROL_BODY_BYTES + 1), 413),
            ("abc", 411), ("-1", 411),
        ):
            with self.subTest(length=length):
                code, error, _ = self.raw_request(
                    "POST", "/api/control", headers={
                        "Content-Type": "application/json",
                        "Content-Length": length,
                    })
                self.assertEqual(code, status)
                self.assertIn("error", error)
        code, error, _ = self.raw_request(
            "POST", "/api/control", headers={"Content-Type": "application/json"})
        self.assertEqual(code, 411)
        self.assertIn("error", error)
        self.assertEqual(self.request("/api/snapshot")[1], first)

    def test_progressive_config_replay_and_atomic_invalid_config(self):
        config = {"assets": [{
            "asset_id": "MTR-99", "name": "Pump example", "scenario": "imbalance",
            "severity": .8, "onset_tick": 2, "duration_ticks": 9,
            "progression": "linear", "start_severity": .2, "ramp_ticks": 4,
        }]}
        self.assertEqual(self.request("/api/config", "PUT", config)[0], 200)
        sequence = [self.request("/api/snapshot")[1]]
        for _ in range(9):
            self.request("/api/control", "POST", {"action": "step"})
            sequence.append(self.request("/api/snapshot")[1])
        self.assertEqual(self.request("/api/control", "POST", {"action": "reset"})[1]["tick"], 1)
        replay = [self.request("/api/snapshot")[1]]
        for _ in range(9):
            self.request("/api/control", "POST", {"action": "step"})
            replay.append(self.request("/api/snapshot")[1])
        self.assertEqual(sequence, replay)
        last = self.request("/api/snapshot")[1]
        for bad in (
            {"assets": []},
            {"assets": [dict(config["assets"][0], ramp_ticks=1)]},
            {"assets": [dict(config["assets"][0], severity=4)]},
        ):
            with self.subTest(config=bad):
                code, error, _ = self.request("/api/config", "PUT", bad)
                self.assertEqual(code, 400)
                self.assertIn("error", error)
                self.assertEqual(self.request("/api/snapshot")[1], last)

    def test_dashboard_load_and_controls(self):
        code, page, _ = self.request("/")
        self.assertEqual(code, 200)
        html = page.decode("utf-8")
        self.assertIn("MotorPulse AI", html)
        for expected in ("/api/snapshot", "/api/config", "/api/control",
                         "progression", "ramp_ticks", "fault_phase", "aria-label"):
            self.assertIn(expected, html)
        parser = DashboardParser()
        parser.feed(html)
        self.assertTrue({"motors", "update", "mode", "config-rows",
                         "config-message"}.issubset(parser.ids))
        self.assertEqual(parser.actions, {"start", "pause", "step", "reset"})
        self.assertGreaterEqual(parser.scripts, 1)


class OfflineReplayContracts(unittest.TestCase):
    def test_cross_seed_profile_replay(self):
        start = datetime(2027, 3, 20, 12, 0, tzinfo=timezone.utc)
        for seed in (1, 42, 123):
            for profile in ("constant", "linear", "exponential"):
                with self.subTest(seed=seed, profile=profile):
                    asset = AssetScenario(
                        "MTR-97", "Repro motor", "bearing_wear", .8,
                        onset_tick=2, duration_ticks=8, progression=profile,
                        start_severity=0 if profile == "constant" else .15,
                        ramp_ticks=None if profile == "constant" else 4,
                    )
                    settings = dict(seed=seed, assets=(asset,),
                                    start_time_utc=start, step_seconds=3.25)
                    a, b = MotorSimulator(**settings), MotorSimulator(**settings)
                    for _ in range(10):
                        left, right = a.step(), b.step()
                        self.assertEqual(left, right)
                        validate_snapshot(left)
                    self.assertEqual(a.tick, 10)
                    self.assertEqual(left["recorded_at_utc"],
                                     "2027-03-20T12:00:29.250000+00:00")

    def test_old_fixture_and_current_schema_compatibility(self):
        with (ROOT / "docs/examples/snapshot-v1.json").open() as handle:
            legacy = json.load(handle)
        validate_snapshot(legacy)
        schema = json.loads((ROOT / "docs/snapshot.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema_version"]["const"],
                         SCHEMA_VERSION)
        current = MotorSimulator().step()
        validate_snapshot(current)
        for field in schema["required"]:
            self.assertIn(field, current)
        for field in schema["$defs"]["asset_event"]["required"]:
            self.assertIn(field, current["assets"][0])
        self.assertIn("progression", current["assets"][0])
        self.assertNotIn("progression", legacy["assets"][0])

    def test_reference_docs_and_examples_parse(self):
        for filename in (
            "docs/SCENARIOS.md", "docs/PROGRESSION.md",
            "docs/TELEMETRY.md", "docs/SIGNALS.md",
            "docs/examples/scenarios-progressive.json",
        ):
            with self.subTest(filename=filename):
                self.assertTrue((ROOT / filename).is_file(), filename)
        configuration = json.loads(
            (ROOT / "docs/examples/scenarios-progressive.json").read_text())
        parse_configuration(configuration)


if __name__ == "__main__":
    unittest.main()
