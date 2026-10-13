"""Thread-safe, local-only simulation control decoupled from HTTP reads."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from pathlib import Path
import sqlite3
from threading import Condition, Thread

from .sim import DEFAULT_START_TIME_UTC, MotorSimulator
from .scenarios import DEFAULT_ASSETS, AssetScenario, parse_configuration, configuration_dict
from .storage import SQLiteHistory

_LOG = logging.getLogger(__name__)


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
                 assets: tuple[AssetScenario, ...] = DEFAULT_ASSETS,
                 database_path: str | Path | None = None) -> None:
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
        self._storage = SQLiteHistory(database_path) if database_path is not None else None
        self._session_id: str | None = None
        self._storage_error: str | None = None
        if self._storage is not None:
            try:
                self._session_id = self._storage.start_session(
                    self._snapshot, seed=seed,
                    start_time_utc=self.start_time_utc.isoformat(),
                    step_seconds=self.step_seconds,
                    configuration=configuration_dict(self._sim.assets),
                    reason="startup",
                )
            except BaseException:
                self._storage.close()
                raise
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
                    try:
                        self._advance_locked()
                    except (sqlite3.Error, OSError, ValueError) as exc:
                        self._running = False
                        self._storage_error = type(exc).__name__
                        _LOG.error("SQLite persistence failed; simulator paused: %s", exc)

    def _require_storage_healthy(self) -> None:
        if self._storage_error is not None:
            raise ControlConflict("persistence error; restart required before simulation writes")

    def _advance_locked(self) -> None:
        """Persist a complete tick before publishing any in-memory change."""
        self._require_storage_healthy()
        # Cloning avoids a partly advanced simulator if an INSERT fails.
        replacement = deepcopy(self._sim) if self._storage is not None else self._sim
        candidate = replacement.step()
        if self._storage is not None:
            assert self._session_id is not None
            self._storage.record(self._session_id, candidate)
        self._sim = replacement
        self._snapshot = candidate

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
            self._require_storage_healthy()
            if self._storage is not None:
                self._session_id = self._storage.start_session(
                    first, seed=self.seed,
                    start_time_utc=self.start_time_utc.isoformat(),
                    step_seconds=self.step_seconds,
                    configuration=configuration_dict(assets), reason="configure",
                )
            self._running = False
            self._sim = replacement
            self._snapshot = first
            self._condition.notify_all()
            return configuration_dict(assets)

    def _status_locked(self) -> dict:
        status = {
                "state": "running" if self._running else "paused",
                "tick": self._sim.tick,
                "seed": self.seed,
                "interval_seconds": self.interval_seconds,
                "step_seconds": self.step_seconds,
                "start_time_utc": self.start_time_utc.isoformat(),
                "simulated_at_utc": self._snapshot["recorded_at_utc"],
            }
        if self._storage is not None:
            status.update({
                "storage": "error" if self._storage_error else "ok",
                "session_id": self._session_id,
            })
        return status

    def status(self) -> dict:
        with self._condition:
            return self._status_locked()

    def control(self, action: str) -> dict:
        if action not in ("start", "pause", "step", "reset"):
            raise ValueError("action must be start, pause, step, or reset")
        with self._condition:
            if self._closed:
                raise ControlConflict("simulation has been closed")
            self._require_storage_healthy()
            if action == "start":
                self._running = True
            elif action == "pause":
                self._running = False
            elif action == "step":
                if self._running:
                    raise ControlConflict("pause the simulation before stepping")
                self._advance_locked()
            elif action == "reset":
                replacement = MotorSimulator(seed=self.seed,
                                             start_time_utc=self.start_time_utc,
                                             step_seconds=self.step_seconds,
                                             assets=self._sim.assets)
                first = replacement.step()
                if self._storage is not None:
                    self._session_id = self._storage.start_session(
                        first, seed=self.seed,
                        start_time_utc=self.start_time_utc.isoformat(),
                        step_seconds=self.step_seconds,
                        configuration=configuration_dict(replacement.assets),
                        reason="reset",
                    )
                self._running = False
                self._sim = replacement
                self._snapshot = first
            self._condition.notify_all()
            return self._status_locked()

    def _history_store(self) -> SQLiteHistory:
        if self._storage is None:
            raise ControlConflict("history requires --database SQLite persistence")
        return self._storage

    def history_snapshots(self, *, session_id: str | None = None,
                          limit: int = 50, before_id: int | None = None,
                          start_utc: str | None = None,
                          end_utc: str | None = None) -> list[dict]:
        with self._condition:
            return self._history_store().snapshots(
                session_id=session_id, limit=limit, before_id=before_id,
                start_utc=start_utc, end_utc=end_utc)

    def history_events(self, *, session_id: str | None = None,
                       asset_id: str | None = None, limit: int = 50,
                       before_id: int | None = None, start_utc: str | None = None,
                       end_utc: str | None = None) -> list[dict]:
        with self._condition:
            return self._history_store().events(
                session_id=session_id, asset_id=asset_id, limit=limit,
                before_id=before_id, start_utc=start_utc, end_utc=end_utc)

    def history_alerts(self, *, session_id: str | None = None,
                       asset_id: str | None = None, limit: int = 50,
                       before_id: int | None = None, start_utc: str | None = None,
                       end_utc: str | None = None) -> list[dict]:
        with self._condition:
            return self._history_store().alerts(
                session_id=session_id, asset_id=asset_id, limit=limit,
                before_id=before_id, start_utc=start_utc, end_utc=end_utc)

    def history_sessions(self, *, limit: int = 50,
                         before_id: int | None = None) -> list[dict]:
        with self._condition:
            return self._history_store().sessions(
                limit=limit, before_id=before_id)

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._running = False
            self._condition.notify_all()
        if self._worker.is_alive():
            self._worker.join(timeout=2)
        if self._storage is not None:
            self._storage.close()

    def __enter__(self) -> SimulationController:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
