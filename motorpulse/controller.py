"""Thread-safe, local-only simulation control decoupled from HTTP reads."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Condition, Thread

from .sim import DEFAULT_START_TIME_UTC, MotorSimulator
from .scenarios import DEFAULT_ASSETS, AssetScenario, parse_configuration, configuration_dict


class ControlConflict(Exception):
    """An action requires the simulator to be in a different state."""


class SimulationController:
    """Own one simulator, its cached snapshot, and a timed background worker.

    Snapshot reads do not mutate state. An initial tick is generated at startup;
    reset returns to the same initial tick and leaves the controller paused.
    Worker scheduling is wall-clock based, but telemetry time is fully virtual.
    """

    def __init__(self, *, seed: int = 42, interval_seconds: float = 1.5,
                 autostart: bool = True,
                 start_time_utc: datetime = DEFAULT_START_TIME_UTC,
                 step_seconds: float = 1.5,
                 assets: tuple[AssetScenario, ...] = DEFAULT_ASSETS) -> None:
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        if not 0 < interval_seconds <= 3600:
            raise ValueError("interval_seconds must be between 0 and 3600")
        self.seed = seed
        self.interval_seconds = interval_seconds
        self._condition = Condition()
        self._sim = MotorSimulator(seed=seed, start_time_utc=start_time_utc,
                                   step_seconds=step_seconds, assets=assets)
        self.start_time_utc = self._sim.start_time_utc
        self.step_seconds = self._sim.step_seconds
        self._snapshot = self._sim.step()
        self._running = bool(autostart)
        self._closed = False
        self._worker = Thread(target=self._run, name="motorpulse-simulator", daemon=True)
        self._worker.start()

    def _run(self) -> None:
        with self._condition:
            while not self._closed:
                if not self._running:
                    self._condition.wait()
                    continue
                # Wait releases the lock; a control action resets this interval.
                notified = self._condition.wait(timeout=self.interval_seconds)
                if self._closed:
                    break
                if not notified and self._running:
                    self._snapshot = self._sim.step()

    def snapshot(self) -> dict:
        with self._condition:
            return deepcopy(self._snapshot)

    def configuration(self) -> dict:
        with self._condition:
            return configuration_dict(self._sim.assets)

    def configure(self, payload: object) -> dict:
        """Atomically replace all asset scenarios and reset to paused tick 1.

        Validation happens before touching any live simulation state.
        """
        assets = parse_configuration(payload)
        replacement = MotorSimulator(seed=self.seed,
                                     start_time_utc=self.start_time_utc,
                                     step_seconds=self.step_seconds,
                                     assets=assets)
        first = replacement.step()
        with self._condition:
            if self._closed:
                raise ControlConflict("simulation has been closed")
            self._running = False
            self._sim = replacement
            self._snapshot = first
            self._condition.notify_all()
            return configuration_dict(assets)

    def status(self) -> dict:
        with self._condition:
            return {
                "state": "running" if self._running else "paused",
                "tick": self._sim.tick,
                "seed": self.seed,
                "interval_seconds": self.interval_seconds,
                "step_seconds": self.step_seconds,
                "start_time_utc": self.start_time_utc.isoformat(),
                "simulated_at_utc": self._snapshot["recorded_at_utc"],
            }

    def control(self, action: str) -> dict:
        if action not in ("start", "pause", "step", "reset"):
            raise ValueError("action must be start, pause, step, or reset")
        with self._condition:
            if self._closed:
                raise ControlConflict("simulation has been closed")
            if action == "start":
                self._running = True
            elif action == "pause":
                self._running = False
            elif action == "step":
                if self._running:
                    raise ControlConflict("pause the simulation before stepping")
                self._snapshot = self._sim.step()
            elif action == "reset":
                self._running = False
                self._sim = MotorSimulator(seed=self.seed,
                                           start_time_utc=self.start_time_utc,
                                           step_seconds=self.step_seconds,
                                           assets=self._sim.assets)
                self._snapshot = self._sim.step()
            self._condition.notify_all()
            return {
                "state": "running" if self._running else "paused",
                "tick": self._sim.tick,
                "seed": self.seed,
                "interval_seconds": self.interval_seconds,
                "step_seconds": self.step_seconds,
                "start_time_utc": self.start_time_utc.isoformat(),
                "simulated_at_utc": self._snapshot["recorded_at_utc"],
            }

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._running = False
            self._condition.notify_all()
        if self._worker.is_alive():
            self._worker.join(timeout=2)

    def __enter__(self) -> SimulationController:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
