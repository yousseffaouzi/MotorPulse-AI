"""Controller lifecycle, concurrent reads and local HTTP contract tests."""
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motorpulse.__main__ import MotorPulseServer
from motorpulse.controller import ControlConflict, SimulationController
from motorpulse.schema import validate_snapshot


class ControllerTests(unittest.TestCase):
    def test_snapshot_does_not_advance(self):
        with SimulationController(autostart=False) as sim:
            first = sim.snapshot()
            self.assertEqual(first, sim.snapshot())
            self.assertEqual(first["tick"], 1)
            validate_snapshot(first)
            self.assertEqual(sim.status()["state"], "paused")
            sim.control("step")
            self.assertEqual(sim.snapshot()["tick"], 2)
            self.assertEqual(sim.snapshot(), sim.snapshot())

    def test_reset_restarts_initial_seed_and_pauses(self):
        with SimulationController(seed=75, autostart=False) as sim:
            initial = sim.snapshot()
            sim.control("step")
            sim.control("step")
            sim.control("reset")
            self.assertEqual(sim.status()["tick"], 1)
            self.assertEqual(sim.status()["state"], "paused")
            self.assertEqual(initial, sim.snapshot())

    def test_background_advances_only_when_started(self):
        with SimulationController(autostart=False, interval_seconds=0.025) as sim:
            sim.control("start")
            limit = time.monotonic() + 1.0
            while sim.status()["tick"] < 3 and time.monotonic() < limit:
                time.sleep(0.005)
            self.assertGreaterEqual(sim.status()["tick"], 3)
            sim.control("pause")
            paused = sim.status()["tick"]
            time.sleep(0.065)
            self.assertEqual(sim.status()["tick"], paused)
            sim.control("start")
            with self.assertRaises(ControlConflict):
                sim.control("step")
            sim.control("pause")

    def test_concurrent_reads_are_independent(self):
        with SimulationController(autostart=False) as sim:
            with ThreadPoolExecutor(max_workers=16) as pool:
                snapshots = list(pool.map(lambda _: sim.snapshot(), range(40)))
            self.assertTrue(all(x == snapshots[0] for x in snapshots))
            self.assertEqual(sim.status()["tick"], 1)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = MotorPulseServer(("127.0.0.1", 0), interval_seconds=0.025,
                                     autostart=False)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.post({"action": "reset"})

    def get(self, path):
        with urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=2) as response:
            return response.status, json.load(response)

    def post(self, body, *, content_type="application/json"):
        data = json.dumps(body).encode("utf-8")
        req = Request(f"http://127.0.0.1:{self.port}/api/control", data=data,
                      headers={"Content-Type": content_type}, method="POST")
        try:
            with urlopen(req, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_get_is_read_only_and_step_is_explicit(self):
        a = self.get("/api/snapshot")[1]
        b = self.get("/api/snapshot")[1]
        self.assertEqual(a, b)
        self.assertEqual(self.get("/api/status")[1]["state"], "paused")
        self.assertEqual(self.post({"action": "step"})[1]["tick"], 2)
        self.assertEqual(self.get("/api/snapshot")[1]["tick"], 2)
        self.assertEqual(self.get("/api/health")[1]["status"], "ok")

    def test_reject_bad_controls(self):
        for body, expected in (([], 400), ({"action": "DROP"}, 400),
                               ({"action": 5}, 400), ({"action": "step", "seed": 1}, 400)):
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0], expected)
        self.assertEqual(self.post({"action": "step"}, content_type="text/plain")[0], 415)
        self.post({"action": "start"})
        self.assertEqual(self.post({"action": "step"})[0], 409)
        self.post({"action": "pause"})

    def test_get_concurrent_stable_and_background_progress(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            observed = list(pool.map(lambda _: self.get("/api/snapshot")[1], range(12)))
        self.assertTrue(all(x == observed[0] for x in observed))
        self.post({"action": "start"})
        limit = time.monotonic() + 1.0
        while self.get("/api/status")[1]["tick"] < 2 and time.monotonic() < limit:
            time.sleep(0.005)
        self.assertGreaterEqual(self.get("/api/status")[1]["tick"], 2)
        self.post({"action": "pause"})
        count = self.get("/api/status")[1]["tick"]
        time.sleep(0.065)
        self.assertEqual(self.get("/api/status")[1]["tick"], count)


if __name__ == "__main__":
    unittest.main()
