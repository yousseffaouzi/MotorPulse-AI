# MP-042 — Persistent synthetic rule-alert incident lifecycle

MotorPulse AI is a localhost-only **synthetic condition-monitoring simulation**. The older MP-012 SQLite database stored one raw rule alert per warning/critical tick. MP-042 adds **deduplicated persistent incident records** and their transitions, without deleting or changing raw alert or telemetry rows. These fictional incidents are not field alarms, industrial diagnoses, validated maintenance decisions or remaining useful life (RUL) predictions.

## Enable and inspect

    python -m motorpulse --paused --database ./motorpulse-local.sqlite3

In the dashboard's Recorded synthetic trends section, select a session and see the Synthetic rule incidents table. It lists the newest 25 grouped incidents, with motor, state, latest severity, opening/last virtual ticks, alerting-tick count and latest reasons. View changes shows up to the newest 100 transitions for a selected incident. Mark reviewed requires an explicit reviewer label, which is **not authenticated**. This marker does not stop or fix a motor, change rule severity or prove that maintenance occurred. Without the opt-in database, the live dashboard still works but recorded incidents are unavailable.

The original GET /api/history/alerts remains **one raw alert record per qualifying tick**. The new incident-level reads are separate.

## Deterministic state transitions

An incident is scoped to a single **recording session UUID and synthetic asset ID**. At most one active incident exists for that pair (enforced by SQLite's partial unique index). Process restarts, simulation resets, runtime changes and scenario changes create independent sessions, never merging deterministic event IDs from different recordings.

| Synthetic observation | Previous state | Result / transition |
| --- | --- | --- |
| Good sensor, warning or critical | No active incident | New active incident; opened |
| Good sensor, unchanged warning/critical and reasons | Active | Update last tick/time and alert_count; no duplicate transition |
| Good sensor, higher or lower severity | Active | Update latest severity/reasons and count; escalated / deescalated |
| Good sensor, same severity but changed reasons | Active | Update latest explanation and count; reasons_changed |
| Good sensor, normal | Active | resolved at that virtual tick, not necessarily physical recovery |
| Missing or suspect/outlier vibration sensor | Active | interrupted; **never infer motor recovery from a damaged sensor** |
| A later warning/critical after resolved/interrupted | No active incident | New incident with a distinct ID |

A severity change with changed reasons yields a single severity transition containing the latest explanation; it does not invent a second condition. There is no inferred industrial debounce, confidence estimate, real alarm hysteresis or safety control. The word active means **not closed within the recording**. A previous session's last open incident must never be interpreted as a real-time alert across a process restart.

An acknowledgement is an **independent, once-only local review annotation**. It never alters the incident's active/resolved/interrupted status, threshold severity, reasons or count. It may be applied to an old recording. Virtual event timestamps are synthetic UTC, while the review's acted_at_utc and acknowledged_at_utc are **real wall-clock UTC**; they cannot be compared as if they were the same clock.

## SQLite schema v3 and migration

The file schema is now SQLite PRAGMA user_version **3**. Existing v1 and v2 files migrate transactionally to v3. New structures:

- **incidents**: recording UUID, motor, state, latest severity/reasons, opening/last/closing virtual ticks and times, alerting-event count, source event and optional reviewer/wall timestamp.
- **incident_transitions**: historical opened, escalated, deescalated, reasons_changed, resolved, interrupted and acknowledged changes with session, motor, source event, virtual timestamp and optional review actor/wall timestamp.
- Database foreign keys, state/kind constraints, a unique active incident per session + motor and bounded-reading indexes.

Migration replays **existing original telemetry rows in their stored insertion order** into incident reductions; it does not rewrite v1/v2 raw telemetry or alerts, and cannot manufacture previous human acknowledgements. Back up the SQLite file before migrating large demo recordings because the replay consumes time and disk. Unknown future schema versions are refused.

A complete tick commits snapshot, per-motor features, original rule events and incident transitions **in one SQLite transaction**. A transition write failure rolls back the whole tick and does not advance the in-memory simulator. Failed reviewer actions roll back both the review fields and transition row.

## REST endpoints

All routes are local-only and use the existing MP-040 versioned envelope and newest-first row-ID cursor contract (limit 1–100, default 50).

| Method | Path | Filters or JSON body |
| --- | --- | --- |
| GET | /api/history/incidents | session_id, asset_id, state=active/resolved/interrupted, before_id, limit |
| GET | /api/history/transitions | incident_id (positive integer), session_id, asset_id, before_id, limit |
| POST | /api/incidents/acknowledge | JSON exactly containing incident_id (positive 64-bit integer) and actor (printable, nonempty, unpadded label of at most 80 characters) |

Example requests:

    curl 'http://127.0.0.1:8765/api/history/incidents?state=active&limit=25'
    curl 'http://127.0.0.1:8765/api/history/transitions?incident_id=1&limit=100'
    curl -X POST 'http://127.0.0.1:8765/api/incidents/acknowledge' -H 'Content-Type: application/json' -d '{"incident_id":1,"actor":"local-demo-reviewer"}'

Successful GET responses retain api_version=1.0.0, source=synthetic, resource, items, page and filters; page has limit, count, has_more, next_before_id and order=id_desc. Incident rows include latest state/severity/reasons and optional reviewed information. Transition rows identify original virtual event evidence separately from any wall-clock reviewer action. Successful POST returns HTTP 200 with source=synthetic_rule and the updated incident object.

| HTTP | Machine code | Meaning |
| --- | --- | --- |
| 400 | invalid_acknowledgement | Invalid POST body, types, incident ID or actor label |
| 400 | invalid_history_query | Invalid incident or transition GET filter |
| 404 | incident_not_found | Requested incident does not exist |
| 409 | incident_already_acknowledged | Review already recorded |
| 409 | history_unavailable | SQLite history not enabled (use --database) |
| 503 | history_storage_error | Persistence operation failed; internal SQL/path details are not disclosed |

No CORS authorization or internet service is added. Actor labels are not verified identities. **Do not port-forward** or use this demonstration for physical alarms, work authorization, incident compliance tracking or real-device control.

## Tests

    python -m unittest discover -s tests -p 'test_incidents.py' -v
    python -m unittest discover -s tests -v

Coverage includes severity/reason changes, deduplication, good-sensor resolution versus sensor interruption, fresh sessions, historical v2-to-v3 backfill, persisted one-time review, SQL rollback, paginated endpoints, validation/errors, packaging and accessible UI contracts. MP-043 general HTTP input hardening and MP-014 optional streaming remain separate tasks.
