"""MP-020: deterministic fault-severity profiles and local API integration."""
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motorpulse.__main__ import MotorPulseServer
from motorpulse.controller import SimulationController
from motorpulse.scenarios import AssetScenario, parse_configuration
from motorpulse.schema import validate_snapshot
from motorpulse.sim import MotorSimulator


def fault(profile="linear", **changes):
    values = dict(asset_id="MTR-99", name="Degrading motor", scenario="imbalance",
                  severity=0.8, onset_tick=3, duration_ticks=9,
                  progression=profile, start_severity=0.0, ramp_ticks=5)
    values.update(changes)
    return AssetScenario(**values)


class ProfileTests(unittest.TestCase):
    def test_linear_onset_ramp_target_and_expiration(self):
        asset = fault()
        data = [asset.effective(t) for t in range(1, 14)]
        self.assertEqual([scenario for scenario, _ in data[:3]], ["healthy"] * 3)
        self.assertEqual([round(severity, 6) for _, severity in data[2:7]],
                         [0.0, 0.2, 0.4, 0.6, 0.8])
        self.assertEqual([severity for _, severity in data[6:11]], [0.8] * 5)
        self.assertEqual(data[11:], [("healthy", 0.0), ("healthy", 0.0)])
        self.assertEqual([asset.phase(t) for t in (1,3,4,7,12)],
                         ["scheduled", "ramping", "ramping", "steady", "ended"])
        self.assertEqual([asset.ramp_fraction(t) for t in (2,3,5,7,12)],
                         [0, 0, .5, 1, 0])

    def test_exponential_is_slow_early_and_monotonic(self):
        linear = fault("linear")
        expo = fault("exponential")
        line = [linear.effective(t)[1] for t in range(3, 8)]
        curve = [expo.effective(t)[1] for t in range(3, 8)]
        self.assertEqual(curve[0], 0)
        self.assertEqual(curve[-1], .8)
        self.assertTrue(all(a < b for a, b in zip(curve, curve[1:])))
        self.assertLess(curve[1], line[1])
        self.assertLess(curve[2], line[2])
        self.assertLess(curve[3], line[3])

    def test_nonzero_start_and_single_tick_boundary(self):
        cfg = fault(onset_tick=1, duration_ticks=None, start_severity=.1,
                    severity=.7, ramp_ticks=2)
        self.assertEqual(cfg.effective(1), ("imbalance", .1))
        self.assertEqual(cfg.effective(2), ("imbalance", .7))
        self.assertEqual(cfg.effective(100000), ("imbalance", .7))
        previous = AssetScenario("MTR-10", "legacy", "imbalance", .6,
                                 onset_tick=3, duration_ticks=1)
        self.assertEqual(previous.effective(2), ("healthy", 0))
        self.assertEqual(previous.effective(3), ("imbalance", .6))
        self.assertEqual(previous.effective(4), ("healthy", 0))

    def test_invalid_curves_rejected(self):
        bad_cases = [
            {"progression":"quadratic"}, {"progression":"linear", "ramp_ticks":None},
            {"ramp_ticks":1}, {"ramp_ticks":True}, {"ramp_ticks":100001},
            {"start_severity":.8}, {"start_severity":1.0},
            {"start_severity":-1}, {"start_severity":float("nan")},
            {"start_severity":True}, {"severity":0}, {"duration_ticks":3},
            {"scenario":"healthy", "severity":0},
        ]
        for delta in bad_cases:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                fault(**delta)
        for delta in [
            {"progression":"constant"},
            {"progression":"constant", "start_severity":.1, "ramp_ticks":None},
        ]:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                fault(**delta)

    def test_roundtrip_optional_legacy_defaults(self):
        base = {"assets":[{"asset_id":"MTR-99","name":"Motor", "scenario":"imbalance", "severity":.6}]}
        parsed = parse_configuration(base)
        self.assertEqual(parsed[0].progression,"constant")
        self.assertIsNone(parsed[0].ramp_ticks)
        self.assertEqual(parse_configuration({"assets":[parsed[0].to_dict()]}),parsed)
        self.assertEqual(parse_configuration({"assets":[fault().to_dict()]}),(fault(),))

    def test_snapshots_are_reproducible_with_progression_metadata(self):
        asset = fault(scenario="overload", severity=1.0, onset_tick=2,
                      duration_ticks=None, ramp_ticks=9)
        a = MotorSimulator(seed=4, assets=(asset,))
        b = MotorSimulator(seed=4, assets=(asset,))
        rows_a, rows_b = [], []
        for _ in range(14):
            snap_a, snap_b = a.step(), b.step()
            validate_snapshot(snap_a)
            self.assertEqual(snap_a, snap_b)
            rows_a.append(snap_a["assets"][0])
            rows_b.append(snap_b["assets"][0])
        self.assertEqual(rows_a, rows_b)
        self.assertEqual(rows_a[0]["fault_phase"], "scheduled")
        self.assertEqual(rows_a[1]["fault_phase"], "ramping")
        self.assertEqual(rows_a[9]["fault_phase"], "steady")
        self.assertEqual(rows_a[-1]["severity"], 1.0)
        self.assertEqual(rows_a[-1]["health"], "critical")
        self.assertEqual(rows_a[0]["health"], "normal")

    def test_reset_matches_every_snapshot(self):
        asset = fault("exponential", onset_tick=1, start_severity=.12,
                      duration_ticks=None)
        with SimulationController(autostart=False, seed=94, assets=(asset,)) as ctrl:
            forward = [ctrl.snapshot()]
            for _ in range(9):
                ctrl.control("step")
                forward.append(ctrl.snapshot())
            ctrl.control("reset")
            repeat = [ctrl.snapshot()]
            for _ in range(9):
                ctrl.control("step")
                repeat.append(ctrl.snapshot())
            self.assertEqual(forward, repeat)


class ProgressionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MotorPulseServer(("127.0.0.1", 0), autostart=False)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_put_progression_and_reject_invalid_atomically(self):
        payload = {"assets": [fault("linear", onset_tick=2).to_dict()]}
        req = Request(self.url + "/api/config", data=json.dumps(payload).encode(),
                      method="PUT", headers={"Content-Type":"application/json"})
        with urlopen(req,timeout=3) as r:
            self.assertEqual(r.status,200)
        def get(path):
            with urlopen(self.url + path, timeout=3) as r:
                return json.load(r)
        self.assertEqual(get("/api/config"),payload)
        self.assertEqual(get("/api/snapshot")["assets"][0]["fault_phase"],"scheduled")
        for _ in range(3):
            req = Request(self.url + "/api/control", data=b'{"action":"step"}',
                          method="POST",headers={"Content-Type":"application/json"})
            with urlopen(req,timeout=3) as r:
                self.assertEqual(r.status,200)
        before = get("/api/snapshot")
        self.assertEqual(before["assets"][0]["progression"],"linear")
        broken = {"assets":[dict(payload["assets"][0],ramp_ticks=1)]}
        req = Request(self.url + "/api/config",data=json.dumps(broken).encode(),
                      method="PUT",headers={"Content-Type":"application/json"})
        with self.assertRaises(HTTPError) as context:
            urlopen(req,timeout=3)
        self.assertEqual(context.exception.code,400)
        self.assertEqual(get("/api/snapshot"),before)


if __name__ == "__main__":
    unittest.main()
