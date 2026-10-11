"""MP-007: reproducible fault configuration and local HTTP integration."""
from __future__ import annotations

from copy import deepcopy
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motorpulse.__main__ import MotorPulseServer
from motorpulse.controller import SimulationController
from motorpulse.schema import validate_snapshot
from motorpulse.scenarios import (
    AssetScenario, DEFAULT_ASSETS, MAX_ASSETS, SCENARIOS,
    configuration_dict, parse_configuration,
)
from motorpulse.sim import MotorSimulator


class ScenarioTests(unittest.TestCase):
    def test_all_scenarios_supported(self):
        self.assertEqual(set(SCENARIOS),
                         {"healthy", "imbalance", "bearing_wear", "misalignment", "overload"})
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                severity = 0 if scenario == "healthy" else 1.0
                a = AssetScenario("MTR-10", "Example", scenario, severity)
                snapshot = MotorSimulator(assets=(a,)).step()
                validate_snapshot(snapshot)
                self.assertEqual(snapshot["assets"][0]["scenario"], scenario)
                self.assertEqual(snapshot, MotorSimulator(assets=(a,)).step())

    def test_default_config_and_roundtrip(self):
        cfg = configuration_dict(DEFAULT_ASSETS)
        self.assertEqual(parse_configuration(cfg), DEFAULT_ASSETS)
        self.assertEqual(len(cfg["assets"]), 3)
        self.assertEqual(cfg["assets"][1]["severity"], 1.0)

    def test_onset_and_duration_are_constant_level(self):
        asset = AssetScenario("MTR-22", "Timeline", "imbalance", 0.6,
                              onset_tick=3, duration_ticks=2)
        sim = MotorSimulator(assets=(asset,))
        observed = [sim.step()["assets"][0] for _ in range(6)]
        self.assertEqual([x["scenario"] for x in observed],
                         ["healthy", "healthy", "imbalance", "imbalance", "healthy", "healthy"])
        self.assertEqual([x["severity"] for x in observed], [0.0, 0.0, 0.6, 0.6, 0.0, 0.0])
        self.assertTrue(all(x["configured_scenario"] == "imbalance" for x in observed))
        self.assertTrue(all(x["duration_ticks"] == 2 for x in observed))
        self.assertTrue(all(x["onset_tick"] == 3 for x in observed))

    def test_severity_influences_signal_and_temperature(self):
        low = MotorSimulator(assets=(AssetScenario("MTR-22", "Test", "imbalance", .3),)).step()["assets"][0]
        high = MotorSimulator(assets=(AssetScenario("MTR-22", "Test", "imbalance", 1.0),)).step()["assets"][0]
        self.assertGreater(high["rms_g"], low["rms_g"])
        self.assertGreater(high["temperature_c"], low["temperature_c"])
        a = MotorSimulator(assets=(AssetScenario("MTR-22", "Test", "overload", 1.0),)).step()["assets"][0]
        self.assertEqual(a["health"], "critical")
        self.assertIn("high temperature", a["reasons"])

    def test_no_op_severity_behaves_as_healthy(self):
        zero = AssetScenario("MTR-10", "Motor", "bearing_wear", severity=0)
        snapshot = MotorSimulator(assets=(zero,)).step()["assets"][0]
        self.assertEqual(snapshot["scenario"], "healthy")
        self.assertEqual(snapshot["severity"], 0)

    def test_rejected_config_cases(self):
        base = configuration_dict(DEFAULT_ASSETS)
        cases = [
            {"other": base["assets"]},
            {"assets": []},
            {"assets": [base["assets"][0]] * 2},
            {"assets": [dict(base["assets"][0], asset_id="unsafe/asset")]},
            {"assets": [dict(base["assets"][0], severity=1)]},
            {"assets": [dict(base["assets"][1], severity=1.1)]},
            {"assets": [dict(base["assets"][1], severity=float("nan"))]},
            {"assets": [dict(base["assets"][1], severity=True)]},
            {"assets": [dict(base["assets"][1], scenario="motor_fire")]},
            {"assets": [dict(base["assets"][1], onset_tick=0)]},
            {"assets": [dict(base["assets"][1], duration_ticks=-1)]},
            {"assets": [dict(base["assets"][1], duration_ticks="2")]},
            {"assets": [dict(base["assets"][1], extra=True)]},
            {"assets": [dict(base["assets"][1], name="")]},
            {"assets": [dict(base["assets"][1], name="a" * 81)]},
            {"assets": [dict(base["assets"][1]) for _ in range(MAX_ASSETS + 1)]},
        ]
        for idx, bad in enumerate(cases):
            with self.subTest(idx=idx), self.assertRaises((ValueError, TypeError)):
                parse_configuration(bad)

    def test_controller_atomic_config_and_reset(self):
        with SimulationController(autostart=False, seed=123) as ctrl:
            new = {"assets": [{"asset_id": "MTR-25", "name": "Test", "scenario": "misalignment",
                               "severity": 0.8, "onset_tick": 2, "duration_ticks": 3}]}
            initial = ctrl.snapshot()
            self.assertEqual(ctrl.configure(new), ctrl.configuration())
            self.assertEqual(ctrl.status()["tick"], 1)
            self.assertEqual(ctrl.status()["state"], "paused")
            self.assertEqual(ctrl.snapshot()["assets"][0]["scenario"], "healthy")
            ctrl.control("step")
            observed = ctrl.snapshot()
            self.assertEqual(observed["assets"][0]["scenario"], "misalignment")
            ctrl.control("reset")
            ctrl.control("step")
            self.assertEqual(ctrl.snapshot(), observed)
            before = ctrl.snapshot()
            with self.assertRaises(ValueError):
                ctrl.configure({"assets": [{"asset_id": "MTR-25", "name": "Test",
                                             "scenario": "wrong", "severity": 1}]})
            self.assertEqual(ctrl.snapshot(), before)
            self.assertNotEqual(initial, before)


class ConfigApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = MotorPulseServer(("127.0.0.1", 0), autostart=False)
        cls.url = f"http://127.0.0.1:{cls.http.server_address[1]}"
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.http.controller.configure(configuration_dict(DEFAULT_ASSETS))

    def request(self, path, method="GET", payload=None, ctype="application/json"):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(self.url + path, data=data, method=method,
                      headers={"Content-Type": ctype} if data is not None else {})
        try:
            with urlopen(req, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as err:
            return err.code, json.load(err)

    def test_config_get_and_put_are_atomic(self):
        status, cfg = self.request("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(cfg, configuration_dict(DEFAULT_ASSETS))
        new = {"assets": [
            {"asset_id": "MTR-11", "name": "Scenario", "scenario": "overload",
             "severity": 1, "onset_tick": 2, "duration_ticks": 2}
        ]}
        self.assertEqual(self.request("/api/config", "PUT", new)[0], 200)
        self.assertEqual(self.request("/api/config")[1]["assets"][0]["asset_id"], "MTR-11")
        self.assertEqual(self.request("/api/status")[1]["state"], "paused")
        self.assertEqual(self.request("/api/snapshot")[1]["tick"], 1)
        self.assertEqual(self.request("/api/snapshot")[1]["assets"][0]["scenario"], "healthy")
        self.request("/api/control", "POST", {"action": "step"})
        self.assertEqual(self.request("/api/snapshot")[1]["assets"][0]["scenario"], "overload")

    def test_invalid_config_does_not_change_snapshot(self):
        original = self.request("/api/snapshot")[1]
        bad = {"assets": [{"asset_id": "x", "name": "X", "scenario": "healthy"}]}
        self.assertEqual(self.request("/api/config", "PUT", bad)[0], 400)
        self.assertEqual(original, self.request("/api/snapshot")[1])
        self.assertEqual(self.request("/api/config", "PUT", configuration_dict(DEFAULT_ASSETS),
                                      ctype="text/plain")[0], 415)
        self.assertEqual(self.request("/api/config", "POST", bad)[0], 404)


if __name__ == "__main__":
    unittest.main()
