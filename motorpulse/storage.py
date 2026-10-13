"""MP-012: optional local SQLite history of synthetic snapshots and rule alerts.

A new persistence session is created on every start/reset/configure, so original
simulated event IDs and timestamps remain perfectly replayable without falsely
deduplicating distinct recordings. This is not an industrial audit log or RUL.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any
from uuid import uuid4

from .schema import validate_snapshot

DATABASE_SCHEMA_VERSION = 2
MAX_PAGE_SIZE = 500
ALERT_STATES = frozenset(("warning", "critical"))
SESSION_REASONS = frozenset(("startup", "reset", "configure"))


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _database_path(path: str | Path) -> Path:
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise ValueError("database path must be a nonempty local filesystem path")
    value = Path(path)
    if str(value) == ":memory:" or str(value).startswith("file:"):
        raise ValueError("database must use a real local file, not SQLite memory/URI")
    if value.is_symlink() or any(parent.is_symlink() for parent in value.parents):
        raise ValueError("database path may not use symlinks")
    if not value.parent.is_dir() or (value.exists() and not value.is_file()):
        raise ValueError("database parent must exist and target must be a regular file")
    return value


def _page(limit: int, before_id: int | None) -> None:
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"history limit must be an integer in [1, {MAX_PAGE_SIZE}]")
    if before_id is not None and (type(before_id) is not int or before_id < 1):
        raise ValueError("history before_id must be a positive integer")


def _filter_text(value: str | None, label: str) -> None:
    if value is not None and (
        type(value) is not str or not 1 <= len(value) <= 128
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"{label} must be 1-128 printable characters")


class SQLiteHistory:
    """A single-process, thread-safe SQLite connection, owned by a controller.

    All snapshot + per-asset telemetry + rule-alert inserts commit together.
    Read methods return a bounded newest-first page; HTTP routing is MP-040.
    """

    def __init__(self, path: str | Path):
        self.path = _database_path(path)
        self._lock = RLock()
        self._closed = False
        self._db = sqlite3.connect(str(self.path), isolation_level=None,
                                   check_same_thread=False, timeout=5.0)
        try:
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA busy_timeout=5000")
            self._migrate()
        except BaseException:
            self._db.close()
            self._closed = True
            raise

    def _migrate(self) -> None:
        with self._lock:
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version > DATABASE_SCHEMA_VERSION:
                    raise ValueError("SQLite history database uses unsupported future schema")
                if version == 0:
                    existing = db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'").fetchall()
                    if existing:
                        raise ValueError("refusing to migrate unrecognized nonempty SQLite database")
                    db.execute("""
                        CREATE TABLE sessions (
                            session_id TEXT PRIMARY KEY,
                            created_at_utc TEXT NOT NULL,
                            seed INTEGER NOT NULL,
                            start_time_utc TEXT NOT NULL,
                            step_seconds REAL NOT NULL,
                            configuration_json TEXT NOT NULL,
                            reason TEXT NOT NULL CHECK(reason IN ('startup','reset','configure'))
                        )
                    """)
                    db.execute("""
                        CREATE TABLE snapshots (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT NOT NULL REFERENCES sessions(session_id),
                            tick INTEGER NOT NULL CHECK(tick >= 1),
                            recorded_at_utc TEXT NOT NULL,
                            snapshot_json TEXT NOT NULL,
                            UNIQUE(session_id, tick)
                        )
                    """)
                    db.execute("""
                        CREATE TABLE telemetry (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
                            session_id TEXT NOT NULL REFERENCES sessions(session_id),
                            event_id TEXT NOT NULL,
                            asset_id TEXT NOT NULL,
                            tick INTEGER NOT NULL CHECK(tick >= 1),
                            timestamp_utc TEXT NOT NULL,
                            health TEXT NOT NULL,
                            sensor_quality TEXT NOT NULL,
                            event_json TEXT NOT NULL,
                            UNIQUE(session_id, event_id),
                            UNIQUE(snapshot_id, asset_id)
                        )
                    """)
                    db.execute("PRAGMA user_version=1")
                    version = 1
                if version == 1:
                    db.execute("""
                        CREATE TABLE rule_alerts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            telemetry_id INTEGER NOT NULL UNIQUE REFERENCES telemetry(id),
                            session_id TEXT NOT NULL REFERENCES sessions(session_id),
                            asset_id TEXT NOT NULL,
                            event_id TEXT NOT NULL,
                            tick INTEGER NOT NULL,
                            timestamp_utc TEXT NOT NULL,
                            severity TEXT NOT NULL CHECK(severity IN ('warning','critical')),
                            reasons_json TEXT NOT NULL,
                            UNIQUE(session_id, event_id)
                        )
                    """)
                    db.execute("CREATE INDEX idx_snapshots_session ON snapshots(session_id,id)")
                    db.execute("CREATE INDEX idx_telemetry_session_asset ON telemetry(session_id,asset_id,id)")
                    db.execute("CREATE INDEX idx_alerts_session_asset ON rule_alerts(session_id,asset_id,id)")
                    db.execute("PRAGMA user_version=2")
                foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
                if foreign_keys:
                    raise ValueError("SQLite history has invalid foreign-key references")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValueError("SQLite history is closed")

    @staticmethod
    def _validate_alerts(snapshot: dict) -> None:
        for event in snapshot["assets"]:
            health = event.get("health")
            quality = event.get("sensor_quality", "good")
            reasons = event.get("reasons")
            if (health in ALERT_STATES and (
                quality != "good" or type(reasons) is not list or not reasons
                or any(type(r) is not str or not r for r in reasons)
            )):
                raise ValueError("alert requires good sensor and explanatory rule reasons")
            if quality != "good" and health in ALERT_STATES:
                raise ValueError("suspect/missing sensors cannot generate rule alerts")

    def _store_snapshot(self, session_id: str, snapshot: dict) -> None:
        db = self._db
        record = db.execute(
            "INSERT INTO snapshots(session_id,tick,recorded_at_utc,snapshot_json) "
            "VALUES (?,?,?,?)",
            (session_id, snapshot["tick"], snapshot["recorded_at_utc"], _json(snapshot)),
        )
        snapshot_id = record.lastrowid
        for event in snapshot["assets"]:
            telemetry = db.execute(
                "INSERT INTO telemetry(snapshot_id,session_id,event_id,asset_id,tick,"
                "timestamp_utc,health,sensor_quality,event_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (snapshot_id, session_id, event["event_id"], event["asset_id"],
                 snapshot["tick"], event["timestamp_utc"], event["health"],
                 event.get("sensor_quality", "good"), _json(event)),
            )
            if event["health"] in ALERT_STATES:
                db.execute(
                    "INSERT INTO rule_alerts(telemetry_id,session_id,asset_id,event_id,"
                    "tick,timestamp_utc,severity,reasons_json) VALUES (?,?,?,?,?,?,?,?)",
                    (telemetry.lastrowid, session_id, event["asset_id"], event["event_id"],
                     snapshot["tick"], event["timestamp_utc"], event["health"],
                     _json(event["reasons"])),
                )

    def start_session(self, snapshot: dict, *, seed: int, start_time_utc: str,
                      step_seconds: float, configuration: dict, reason: str) -> str:
        validate_snapshot(snapshot)
        self._validate_alerts(snapshot)
        if reason not in SESSION_REASONS:
            raise ValueError("invalid simulation session reason")
        session_id = str(uuid4())
        with self._lock:
            self._ensure_open()
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "INSERT INTO sessions(session_id,created_at_utc,seed,start_time_utc,"
                    "step_seconds,configuration_json,reason) VALUES(?,?,?,?,?,?,?)",
                    (session_id, datetime.now(timezone.utc).isoformat(), seed,
                     start_time_utc, step_seconds, _json(configuration), reason),
                )
                self._store_snapshot(session_id, snapshot)
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return session_id

    def record(self, session_id: str, snapshot: dict) -> None:
        validate_snapshot(snapshot)
        self._validate_alerts(snapshot)
        _filter_text(session_id, "session_id")
        if session_id is None:
            raise ValueError("session_id is required")
        with self._lock:
            self._ensure_open()
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                self._store_snapshot(session_id, snapshot)
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def sessions(self, *, limit: int = 50) -> list[dict]:
        _page(limit, None)
        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                "SELECT session_id,created_at_utc,seed,start_time_utc,step_seconds,"
                "configuration_json,reason FROM sessions ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            dict(session_id=r[0], created_at_utc=r[1], seed=r[2], start_time_utc=r[3],
                 step_seconds=r[4], configuration=json.loads(r[5]), reason=r[6])
            for r in rows
        ]

    def snapshots(self, *, session_id: str | None = None, limit: int = 50,
                  before_id: int | None = None) -> list[dict]:
        _page(limit, before_id)
        _filter_text(session_id, "session_id")
        where = []
        params: list = []
        if session_id is not None:
            where.append("session_id=?")
            params.append(session_id)
        if before_id is not None:
            where.append("id<?")
            params.append(before_id)
        condition = " WHERE " + " AND ".join(where) if where else ""
        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                "SELECT id,session_id,snapshot_json FROM snapshots" + condition +
                " ORDER BY id DESC LIMIT ?", (*params, limit),
            ).fetchall()
        return [{"id":r[0], "session_id":r[1], "snapshot":json.loads(r[2])} for r in rows]

    def events(self, *, session_id: str | None = None, asset_id: str | None = None,
               limit: int = 50, before_id: int | None = None) -> list[dict]:
        _page(limit, before_id)
        _filter_text(session_id, "session_id")
        _filter_text(asset_id, "asset_id")
        where = []
        params: list = []
        for key, value in (("session_id", session_id), ("asset_id", asset_id)):
            if value is not None:
                where.append(key+"=?")
                params.append(value)
        if before_id is not None:
            where.append("id<?")
            params.append(before_id)
        condition = " WHERE "+" AND ".join(where) if where else ""
        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                "SELECT id,session_id,event_json FROM telemetry" + condition +
                " ORDER BY id DESC LIMIT ?", (*params, limit),
            ).fetchall()
        return [{"id":r[0], "session_id":r[1], "event":json.loads(r[2])} for r in rows]

    def alerts(self, *, session_id: str | None = None, asset_id: str | None = None,
               limit: int = 50, before_id: int | None = None) -> list[dict]:
        _page(limit, before_id)
        _filter_text(session_id, "session_id")
        _filter_text(asset_id, "asset_id")
        where = []
        params: list = []
        for key, value in (("session_id", session_id), ("asset_id", asset_id)):
            if value is not None:
                where.append(key+"=?")
                params.append(value)
        if before_id is not None:
            where.append("id<?")
            params.append(before_id)
        condition = " WHERE "+" AND ".join(where) if where else ""
        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                "SELECT id,session_id,asset_id,event_id,tick,timestamp_utc,"
                "severity,reasons_json FROM rule_alerts" + condition +
                " ORDER BY id DESC LIMIT ?", (*params, limit),
            ).fetchall()
        return [
            dict(id=r[0], session_id=r[1], asset_id=r[2], event_id=r[3],
                 tick=r[4], timestamp_utc=r[5], severity=r[6],
                 reasons=json.loads(r[7]), source="synthetic_rule")
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._db.close()

    def __enter__(self) -> SQLiteHistory:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
