"""Independent UTC virtual time and exact deterministic replay tests."""
from datetime import datetime, timedelta, timezone
import math
import unittest

from motorpulse.controller import SimulationController
from motorpulse.schema import validate_snapshot
from motorpulse.sim import MotorSimulator, parse_start_time_utc


class VirtualClockTests(unittest.TestCase):
    def test_identical_seed_and_config_replay_identically(self):
        start = parse_start_time_utc("2026-09-01T04:00:00Z")
        a = MotorSimulator(seed=13, start_time_utc=start, step_seconds=2.25)
        b = MotorSimulator(seed=13, start_time_utc=start, step_seconds=2.25)
        snapshots_a = [a.step() for _ in range(5)]
        snapshots_b = [b.step() for _ in range(5)]
        self.assertEqual(snapshots_a, snapshots_b)
        for i, snapshot in enumerate(snapshots_a):
            self.assertEqual(snapshot["recorded_at_utc"],
                             (start + timedelta(seconds=i * 2.25)).isoformat())
            validate_snapshot(snapshot)

    def test_fractional_microsecond_increment(self):
        sim = MotorSimulator(step_seconds=0.000001)
        self.assertEqual(sim.step()["recorded_at_utc"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(sim.step()["recorded_at_utc"], "2026-01-01T00:00:00.000001+00:00")

    def test_reset_replay_independent_of_auto_timer(self):
        start = parse_start_time_utc("2030-01-01T00:00:00Z")
        with SimulationController(seed=91, interval_seconds=30, autostart=False,
                                  start_time_utc=start, step_seconds=0.5) as sim:
            first_run = [sim.snapshot()]
            first_run.extend(sim.snapshot() for _ in range(4))
            self.assertEqual(len({s["tick"] for s in first_run}), 1)
            sequence = [sim.snapshot()]
            for _ in range(3):
                sim.control("step")
                sequence.append(sim.snapshot())
            self.assertEqual(sim.status()["simulated_at_utc"], sequence[-1]["recorded_at_utc"])
            self.assertEqual(sim.status()["step_seconds"], 0.5)
            sim.control("reset")
            replay = [sim.snapshot()]
            for _ in range(3):
                sim.control("step")
                replay.append(sim.snapshot())
            self.assertEqual(sequence, replay)

    def test_variable_wall_clock_interval_does_not_change_virtual_time(self):
        start = parse_start_time_utc("2028-12-31T23:59:59Z")
        with SimulationController(autostart=False, interval_seconds=0.01,
                                  start_time_utc=start, step_seconds=3.0) as fast, \
             SimulationController(autostart=False, interval_seconds=100,
                                  start_time_utc=start, step_seconds=3.0) as slow:
            for _ in range(3):
                self.assertEqual(fast.snapshot(), slow.snapshot())
                fast.control("step")
                slow.control("step")

    def test_cli_timestamp_parsing_and_invalid_configuration(self):
        self.assertEqual(parse_start_time_utc("2026-01-01T00:00:00+00:00"),
                         datetime(2026, 1, 1, tzinfo=timezone.utc))
        for invalid in ("bad", "2026-01-01T00:00:00", "2026-01-01T01:00:00+01:00"):
            with self.subTest(when=invalid), self.assertRaises(ValueError):
                parse_start_time_utc(invalid)
        for step in (0, -1, 0.0000001, math.inf, math.nan, "2", True):
            with self.subTest(step=step), self.assertRaises(ValueError):
                MotorSimulator(step_seconds=step)
        with self.assertRaises(ValueError):
            MotorSimulator(start_time_utc=datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
