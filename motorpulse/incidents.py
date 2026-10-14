"""MP-042: durable synthetic rule incident reducer and explicit operator actions.

Incidents are grouped only within an isolated simulator session/asset. A
"live" incident is unresolved in *that recording*, never a real machine alarm.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

KINDS = frozenset(("opened", "escalated", "deescalated", "reasons_changed",
                   "resolved", "interrupted", "acknowledged"))
STATES = frozenset(("active", "resolved", "interrupted"))
SEVERITY = {"warning": 1, "critical": 2}


class IncidentNotFound(Exception):
    """No incident with the requested SQLite identifier."""


class IncidentConflict(Exception):
    """Conflicting acknowledgement request."""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def create_tables(db: sqlite3.Connection) -> None:
    """Idempotency is secured by schema version and the caller's transaction."""
    db.execute("""
        CREATE TABLE incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            asset_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('active','resolved','interrupted')),
            severity TEXT NOT NULL CHECK(severity IN ('warning','critical')),
            reasons_json TEXT NOT NULL,
            opened_tick INTEGER NOT NULL,
            opened_at_utc TEXT NOT NULL,
            last_tick INTEGER NOT NULL,
            last_at_utc TEXT NOT NULL,
            last_event_id TEXT NOT NULL,
            alert_count INTEGER NOT NULL CHECK(alert_count>=1),
            closed_tick INTEGER,
            closed_at_utc TEXT,
            acknowledged_at_utc TEXT,
            acknowledged_by TEXT,
            CHECK((state='active' AND closed_tick IS NULL AND closed_at_utc IS NULL)
                  OR (state!='active' AND closed_tick IS NOT NULL AND closed_at_utc IS NOT NULL)),
            CHECK((acknowledged_at_utc IS NULL)=(acknowledged_by IS NULL))
        )
    """)
    db.execute("""
        CREATE TABLE incident_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL REFERENCES incidents(id),
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            asset_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN
                ('opened','escalated','deescalated','reasons_changed',
                 'resolved','interrupted','acknowledged')),
            tick INTEGER NOT NULL,
            timestamp_utc TEXT NOT NULL,
            from_severity TEXT,
            to_severity TEXT,
            reasons_json TEXT NOT NULL,
            event_id TEXT NOT NULL,
            actor TEXT,
            acted_at_utc TEXT,
            CHECK((kind='acknowledged' AND actor IS NOT NULL AND acted_at_utc IS NOT NULL)
                  OR (kind!='acknowledged' AND actor IS NULL AND acted_at_utc IS NULL))
        )
    """)
    db.execute("""
        CREATE UNIQUE INDEX idx_incidents_active
        ON incidents(session_id,asset_id) WHERE state='active'
    """)
    db.execute("CREATE INDEX idx_incidents_session_asset ON incidents(session_id,asset_id,id)")
    db.execute("CREATE INDEX idx_transitions_incident ON incident_transitions(incident_id,id)")


def _transition(db: sqlite3.Connection, incident_id: int, session_id: str,
                asset_id: str, kind: str, tick: int, timestamp_utc: str,
                old: str | None, new: str | None, reasons: list,
                event_id: str, *, actor: str | None = None,
                acted_at_utc: str | None = None) -> None:
    db.execute("""
        INSERT INTO incident_transitions
        (incident_id,session_id,asset_id,kind,tick,timestamp_utc,from_severity,
         to_severity,reasons_json,event_id,actor,acted_at_utc)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    """, (incident_id,session_id,asset_id,kind,tick,timestamp_utc,
          old,new,_json(reasons),event_id,actor,acted_at_utc))


def reduce_event(db: sqlite3.Connection, session_id: str, tick: int,
                 event: dict) -> None:
    """Consume one already validated per-motor event inside the caller transaction."""
    asset_id = event["asset_id"]
    quality = event.get("sensor_quality", "good")
    health = event["health"]
    at = event["timestamp_utc"]
    event_id = event["event_id"]
    reasons = event.get("reasons", [])
    prior = db.execute("""
        SELECT id,severity,reasons_json FROM incidents
        WHERE session_id=? AND asset_id=? AND state='active'
    """, (session_id,asset_id)).fetchone()
    if not prior:
        if quality != "good" or health not in SEVERITY:
            return
        cursor = db.execute("""
            INSERT INTO incidents
                (session_id,asset_id,state,severity,reasons_json,opened_tick,
                 opened_at_utc,last_tick,last_at_utc,last_event_id,alert_count)
            VALUES(?,?,'active',?,?,?,?,?,?,?,1)
        """, (session_id,asset_id,health,_json(reasons),
              tick,at,tick,at,event_id))
        _transition(db,cursor.lastrowid,session_id,asset_id,"opened",tick,at,
                    None,health,reasons,event_id)
        return
    incident_id, old_severity, old_reasons = prior
    if quality != "good" or health in ("unavailable", "suspect"):
        # A broken sensor does not prove a machine recovered; end as interrupted.
        db.execute("""
            UPDATE incidents SET state='interrupted',closed_tick=?,closed_at_utc=?,
                last_tick=?,last_at_utc=?,last_event_id=?
            WHERE id=?
        """, (tick,at,tick,at,event_id,incident_id))
        _transition(db,incident_id,session_id,asset_id,"interrupted",tick,at,
                    old_severity,old_severity,reasons,event_id)
    elif health == "normal":
        db.execute("""
            UPDATE incidents SET state='resolved',closed_tick=?,closed_at_utc=?,
                last_tick=?,last_at_utc=?,last_event_id=?
            WHERE id=?
        """, (tick,at,tick,at,event_id,incident_id))
        _transition(db,incident_id,session_id,asset_id,"resolved",tick,at,
                    old_severity,None,reasons,event_id)
    elif health in SEVERITY:
        kind = ("escalated" if SEVERITY[health] > SEVERITY[old_severity] else
                "deescalated" if SEVERITY[health] < SEVERITY[old_severity] else
                "reasons_changed" if _json(reasons) != old_reasons else None)
        db.execute("""
            UPDATE incidents SET severity=?,reasons_json=?,last_tick=?,
                last_at_utc=?,last_event_id=?,alert_count=alert_count+1 WHERE id=?
        """, (health,_json(reasons),tick,at,event_id,incident_id))
        if kind:
            _transition(db,incident_id,session_id,asset_id,kind,tick,at,
                        old_severity,health,reasons,event_id)


def backfill(db: sqlite3.Connection) -> None:
    """Reconstruct v3 incidents from original v2 per-event telemetry in row order."""
    cursor = db.execute("""
        SELECT session_id,tick,event_json FROM telemetry ORDER BY id
    """)
    for session_id,tick,event_json in cursor:
        reduce_event(db,session_id,tick,json.loads(event_json))


def row_to_incident(row: tuple) -> dict:
    return dict(
        id=row[0],session_id=row[1],asset_id=row[2],state=row[3],
        severity=row[4],reasons=json.loads(row[5]),opened_tick=row[6],
        opened_at_utc=row[7],last_tick=row[8],last_at_utc=row[9],
        last_event_id=row[10],alert_count=row[11],closed_tick=row[12],
        closed_at_utc=row[13],acknowledged_at_utc=row[14],acknowledged_by=row[15],
        source="synthetic_rule",
    )


INCIDENT_SELECT = (
    "SELECT id,session_id,asset_id,state,severity,reasons_json,opened_tick,"
    "opened_at_utc,last_tick,last_at_utc,last_event_id,alert_count,"
    "closed_tick,closed_at_utc,acknowledged_at_utc,acknowledged_by FROM incidents"
)


def acknowledge(db: sqlite3.Connection, incident_id: int, actor: str) -> dict:
    """Explicit once-only label, not a real operating maintenance acknowledgement."""
    if type(incident_id) is not int or not 1 <= incident_id <= 2**63-1:
        raise ValueError("incident_id must be a positive SQLite 64-bit integer")
    if (type(actor) is not str or not 1 <= len(actor) <= 80
            or actor != actor.strip() or any(ord(c) < 32 or ord(c) == 127 for c in actor)):
        raise ValueError("actor must be a nonempty, unpadded printable label of at most 80 characters")
    row = db.execute(INCIDENT_SELECT+" WHERE id=?", (incident_id,)).fetchone()
    if row is None:
        raise IncidentNotFound("incident not found")
    if row[14] is not None:
        raise IncidentConflict("incident is already acknowledged")
    acted_at = datetime.now(timezone.utc).isoformat()
    db.execute("""
        UPDATE incidents SET acknowledged_at_utc=?,acknowledged_by=? WHERE id=?
    """, (acted_at,actor,incident_id))
    incident=row_to_incident(row)
    _transition(db,incident_id,incident["session_id"],incident["asset_id"],
                "acknowledged",incident["last_tick"],incident["last_at_utc"],
                incident["severity"],incident["severity"],incident["reasons"],
                incident["last_event_id"],actor=actor,acted_at_utc=acted_at)
    updated = db.execute(INCIDENT_SELECT+" WHERE id=?", (incident_id,)).fetchone()
    return row_to_incident(updated)
