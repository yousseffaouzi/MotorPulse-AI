# MP-012 — Optional SQLite telemetry and rule-alert history

MotorPulse-AI can persist **simulated feature snapshots**, per-motor synthetic telemetry and **illustrative rule warning/critical events** to a local SQLite file. The memory-only demo remains the default: no database is created unless explicitly requested. Uses Python standard-library sqlite3 only. This is not physical motor fault validation, RUL inference or a production audit system.

## Running locally

    python -m motorpulse --paused --database ./motorpulse-local.sqlite3

Open the localhost address printed by the server and step, start, pause, reset or configure as before. The SQLite file remains after the process exits. Reopen the same path to make a **new persistence session at tick 1** while old history stays readable:

    python -m motorpulse --paused --database ./motorpulse-local.sqlite3

This is deliberate: deterministic seed/time/event-ID replay is unchanged, and a new random session UUID separates distinct observations. Reset and scenario configuration also create new sessions with reasons startup, reset or configure. The simulator does **not** resume an old wall-clock state or pick up an old running tick.

## Versioned schema

The SQLite file uses PRAGMA user_version=2:

- **v1:** sessions (random ID, seed, virtual UTC start, step interval, scenario JSON and reason); snapshots (session, tick, timestamp and full telemetry-schema JSON); telemetry (per-asset complete event JSON, health, sensor quality, source IDs, timestamps, linked to snapshot/session).
- **v2:** rule_alerts (only warning or critical rule decisions on good sensors, linked to the original telemetry row, including rule reasons), plus indexed history reads.

New files migrate 0→1→2. Valid v1 databases migrate to v2 transactionally. All persisted v1 telemetry remains accessible. Unknown populated unversioned SQLite databases and versions newer than 2 are refused. Schema includes foreign keys and unique session/tick/event constraints. Back up locally before any future schema migration.

**Each tick is a single transaction:** full snapshot, every asset event and any derived rule-alert events commit together. A failed SQL write rolls back that tick. Synchronous failures do not advance the in-memory simulator or swap configurations. The background worker pauses on storage failure, and the local status response shows storage=error. Correct the file or disk problem and restart; no silent telemetry loss is reported as success.

Existing GET /api/snapshot stays read-only. Existing live snapshot/status/control/config API behavior remains compatible; enabling persistence adds storage and session_id to status. Synchronous SQLite write failures are reported by the server as HTTP 503. **MP-040 implements the read-only history/event REST endpoints** on top of these controller methods, with bounded validated input. See [HISTORY_API.md](HISTORY_API.md).

## Querying local history

Python controller methods wrap bounded, parameterized SQLite reads:

    controller.history_sessions(limit=50)
    controller.history_snapshots(session_id=None, limit=50, before_id=None)
    controller.history_events(session_id=None, asset_id=None, limit=50, before_id=None)
    controller.history_alerts(session_id=None, asset_id=None, limit=50, before_id=None)

All return newest-first lists, with page sizes 1–500 and an exclusive ascending row-ID before_id cursor to page backward. Stored JSON round-trips include UTC timestamps, sensor quality, calibrated units, scenario metadata and synthetic truth. Only feature summaries are persisted; raw 1024-sample vibration arrays are **not** included.

The database must be a regular local file with an existing parent directory and no symlinks in its path. SQLite URI strings and :memory: are refused because this mode guarantees a durable file. Protect the file with operating-system permissions. No remote/cloud database, retention policy, application authentication, data-at-rest encryption or multi-process writer coordination is provided. The server still binds to 127.0.0.1.

## MP-013 browser history visualization

The [historical trend dashboard](HISTORICAL_DASHBOARD.md) now queries SQLite through the bounded, read-only MP-040 HTTP API, never through a browser-side database connection. It plots synthetic vibration RMS (g), temperature (°C) and RPM, and shows original sensor quality in an expandable table. Persistent sessions remain distinct across resets/restarts. Charts do not interpolate missing/outlier vibration measurements and do not imply hardware health validation.

## Meaning of persisted alerts

Only the existing fixed-rule health warning/critical decisions with good sensor quality are stored as **synthetic rule alerts**. Missing/outlier sensor windows remain in telemetry as unavailable/suspect, never converted into trustworthy motor diagnoses. Every alert-producing tick produces a row even if an alert persists; acknowledgement, deduplication, transitions and lifecycle policy are separate **MP-042** work.

The offline MP-010 learned anomaly detector is **not silently wired to the live alert pipeline**. The storage infrastructure does not ingest real bearing archives, reach PLC equipment, make physical prognostic claims or estimate remaining useful life.

## Verification

    python -m unittest discover -s tests -p 'test_storage.py' -v
    python -m unittest discover -s tests -v

Tests cover schema creation, v1→v2 migration, unsupported/foreign databases, lossless JSON readback, restart and configuration/reset session separation, alerts/sensor quality, source identity collision isolation, SQL transaction rollback, background fail-closed behavior, pagination and parameterized filtering, concurrency, HTTP integration, bad paths and no-file default.

**Next:** MP-013 accessible historical charts; MP-042 explicit rule-alert lifecycle. MP-040 REST endpoints are now implemented, described in [HISTORY_API.md](HISTORY_API.md). This milestone is persistence infrastructure for a reproducible educational simulator, **not evidence of industrial diagnostic accuracy**.
