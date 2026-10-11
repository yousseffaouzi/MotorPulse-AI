"""Thread-safe, local-only simulation control decoupled from HTTP reads."""
from __future__ import annotations

from copy import deepcopy
from threading import Condition, Thread

from .sim import MotorSimulator


class ControlConflict(Exception):
    """An action requires the simulator to be in a different state."""


class SimulationController:
    """Own one simulator, its cached snapshot, and a timed background worker.

    Snapshot reads do not mutate state. An initial tick is generated at startup;
    reset returns to the same initial tick and leaves the controller paused.
    This is wall-clock scheduling; a virtual simulation clock is MP-018.
    """

    def __init__(self, *, seed: int = 42, interval_seconds: float = 1.5,
                 autostart: bool = True) -> None:
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        if not 0 < interval_seconds <= 3600:
            raise ValueError("interval_seconds must be between 0 and 3600")
        self.seed = seed
        self.interval_seconds = interval_seconds
        self._condition = Condition()
        self._sim = MotorSimulator(seed=seed)
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

    def status(self) -> dict:
        with self._condition:
            return {
                "state": "running" if self._running else "paused",
                "tick": self._sim.tick,
                "seed": self.seed,
                "interval_seconds": self.interval_seconds,
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
                self._sim = MotorSimulator(seed=self.seed)
                self._snapshot = self._sim.step()
            self._condition.notify_all()
            return {
                "state": "running" if self._running else "paused",
                "tick": self._sim.tick,
                "seed": self.seed,
                "interval_seconds": self.interval_seconds,
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
