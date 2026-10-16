# MotorPulse AI localhost API reference

MotorPulse AI exposes a **local-only synthetic simulation API** from the standard-library HTTP server in `motorpulse/__main__.py`. It binds to `127.0.0.1`; it is not an authenticated production service, a remote-control interface, or a physical motor diagnostic API. Do not port-forward it or connect it to machinery.

The default base URL is `http://127.0.0.1:8765`. Use `--port` to select another loopback port. All JSON responses set `Content-Type: application/json; charset=utf-8`, `Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`.

## Route summary

| Method | Path | Purpose | Persistence required? |
| --- | --- | --- | --- |
| GET | `/api/health` | Process/API liveness for the synthetic app | No |
| GET | `/api/snapshot` | Read the cached current telemetry snapshot without stepping | No |
| GET | `/api/status` | Read controller state, seed, clocks, tick and optional storage/session status | No |
| GET | `/api/config` | Read the complete active per-asset synthetic scenario configuration | No |
| PUT | `/api/config` | Atomically validate and replace all asset scenarios, pause and reset | No |
| PUT | `/api/runtime` | Atomically replace deterministic seed and clock settings, pause and reset | No |
| POST | `/api/control` | `start`, `pause`, `step`, or `reset` the synthetic controller | No |
| GET | `/api/history/sessions` | Read newest-first recorded SQLite sessions | Yes |
| GET | `/api/history/snapshots` | Read recorded snapshot rows | Yes |
| GET | `/api/history/events` | Read recorded per-asset telemetry/event rows | Yes |
| GET | `/api/history/alerts` | Read original per-tick synthetic rule-alert rows | Yes |
| GET | `/api/history/incidents` | Read deduplicated synthetic rule incidents | Yes |
| GET | `/api/history/transitions` | Read incident lifecycle/review transitions | Yes |
| POST | `/api/incidents/acknowledge` | Add a once-only local reviewer annotation to one recorded incident | Yes |

There is no `GET /api/runtime`. Current runtime settings are part of `GET /api/status`.

## Read-only live endpoints

### `GET /api/health`

Returns HTTP 200:

```json
{"status":"ok","source":"simulation"}
```

This only proves that the local demo HTTP process is responding. It is not a health assessment of physical equipment.

### `GET /api/snapshot`

Returns the cached v1 synthetic telemetry snapshot. Reads are side-effect free: polling does not advance virtual time or write a new tick. The authoritative field contract is [TELEMETRY.md](TELEMETRY.md), with machine-readable structure in [snapshot.schema.json](snapshot.schema.json).

### `GET /api/status`

Returns controller state and timing metadata, including `state`, `tick`, `seed`, `start_time_utc`, `simulated_at_utc`, `step_seconds`, and `interval_seconds`. When SQLite persistence is enabled, status also exposes local storage/session metadata. See [RUNTIME_CONTROLS.md](RUNTIME_CONTROLS.md).

### `GET /api/config`

Returns the same complete `{ "assets": [...] }` configuration shape accepted by `PUT /api/config`. Scenario fields and ranges are documented in [SCENARIOS.md](SCENARIOS.md), [PROGRESSION.md](PROGRESSION.md), and [OPERATIONS.md](OPERATIONS.md).

## Mutation endpoints

All request bodies below must use `Content-Type: application/json` and a valid positive `Content-Length`.

### `POST /api/control`

The body must contain exactly one string field:

```json
{"action":"pause"}
```

Accepted actions are `start`, `pause`, `step`, and `reset`. `step` is valid only while paused. Configuration/runtime changes and reset produce deterministic replay semantics described in [SIMULATION_CONTROL.md](SIMULATION_CONTROL.md).

Common failures:

| HTTP | `code` | Meaning |
| --- | --- | --- |
| 400 | `invalid_control_request` | Wrong body shape, type, or action |
| 409 | `control_conflict` | State transition is not allowed, such as stepping while running |
| 503 | `persistence_unavailable` | Required SQLite write failed; live state is not advanced/claimed committed |

### `PUT /api/config`

Accepts exactly the validated asset configuration used by local `--config` files:

```json
{
  "assets": [
    {"asset_id":"MTR-01","name":"Conveyor","scenario":"healthy","severity":0}
  ]
}
```

The full replacement is validated before mutation. A successful change pauses the simulation and resets to tick 1 while preserving the active seed/clock settings. With SQLite enabled, the new initial snapshot is persisted as a distinct recording session before the live configuration is published.

Common failures use `invalid_configuration` (400), `control_conflict` (409), or `persistence_unavailable` (503). See [CONFIG_FILE.md](CONFIG_FILE.md) for the important difference between the trusted-local startup file boundary and this HTTP boundary.

### `PUT /api/runtime`

Requires exactly all three fields:

```json
{
  "seed": 1357,
  "step_seconds": 0.5,
  "interval_seconds": 1.5
}
```

This replaces the deterministic PRNG seed, virtual seconds-per-tick, and real worker cadence, then pauses/resets to tick 1. It preserves the current asset scenarios and virtual UTC epoch. Detailed ranges and atomicity guarantees are in [RUNTIME_CONTROLS.md](RUNTIME_CONTROLS.md).

Common failures use `invalid_runtime_settings` (400), `control_conflict` (409), or `persistence_unavailable` (503).

### `POST /api/incidents/acknowledge`

Requires exactly:

```json
{"incident_id":1,"actor":"local-demo-reviewer"}
```

The reviewer label is **not an authenticated identity**. The action only adds a once-only local review annotation; it does not resolve an incident, change severity, authorize maintenance, or control equipment. See [ALERT_LIFECYCLE.md](ALERT_LIFECYCLE.md).

Specific codes are `invalid_acknowledgement` (400), `incident_not_found` (404), `incident_already_acknowledged` (409), `history_unavailable` (409), and `history_storage_error` (503).

## History API

History is opt-in. Start with a local database path:

```bash
python -m motorpulse --paused --database ./motorpulse-local.sqlite3
```

The six `GET /api/history/...` routes use API envelope version `1.0.0`, `source="synthetic"`, newest-first row-ID pagination, default limit 50, maximum limit 100, and a maximum raw query-string size of 2048 bytes.

| Resource | Extra filters in addition to `limit` / `before_id` |
| --- | --- |
| sessions | none |
| snapshots | `session_id`, `start_utc`, `end_utc` |
| events | `session_id`, `asset_id`, `start_utc`, `end_utc` |
| alerts | `session_id`, `asset_id`, `start_utc`, `end_utc` |
| incidents | `session_id`, `asset_id`, `state=active|resolved|interrupted` |
| transitions | `session_id`, `asset_id`, `incident_id` |

Unknown, duplicate, empty/padded, malformed-percent-encoded, or resource-inapplicable query fields are rejected rather than ignored. UTC range semantics, cursor examples, and response fields are detailed in [HISTORY_API.md](HISTORY_API.md); incident lifecycle semantics are in [ALERT_LIFECYCLE.md](ALERT_LIFECYCLE.md).

History failures use:

- 400 `invalid_history_query` for query validation errors;
- 409 `history_unavailable` when the app was not started with `--database`;
- 503 `history_storage_error` when SQLite access fails without disclosing SQL or local filesystem paths.

## Strict JSON request boundary (MP-043)

`POST`/`PUT` API bodies are deliberately small and strict:

- maximum body size: **16384 bytes**;
- `Content-Type` must be `application/json` (parameters such as charset are tolerated after the media type);
- `Content-Length` is required, decimal, positive, and bounded before integer conversion;
- UTF-8 decoding must succeed;
- duplicate object keys are rejected at every level;
- non-standard JSON constants `NaN`, `Infinity`, and `-Infinity` are rejected;
- maximum parsed JSON nesting depth: **64**;
- invalid input is rejected before controller mutation.

Framing/parser codes are stable:

| HTTP | `code` | Condition |
| --- | --- | --- |
| 415 | `unsupported_media_type` | Body media type is not JSON |
| 411 | `length_required` | Missing/malformed `Content-Length` |
| 413 | `invalid_request_size` | Empty or larger-than-allowed body |
| 400 | `invalid_json` | Bad UTF-8/JSON, duplicate keys, non-standard constants, or excessive nesting |

For an unknown `/api/...` path—or unsupported `DELETE`, `PATCH`, or `OPTIONS` against an API path—the server returns 404 JSON with `code="unknown_api_endpoint"`. `HEAD` on an API path returns the same 404 JSON headers with no body. Static-file unsupported methods keep the standard HTTP-server behavior. No CORS preflight permission is granted.

## Error object shape

API errors are JSON objects with a human-readable `error` string and stable machine-readable `code` where the current contract defines one:

```json
{"error":"Unknown API endpoint","code":"unknown_api_endpoint"}
```

Do not parse the human text as a stable protocol. Branch on documented `code` values and HTTP status instead.

## Safety and scope

- The server binds to **127.0.0.1** only; there is no supported public-network mode.
- There is no authentication/authorization layer. Incident actor labels are not identities.
- There is no PLC, actuator, sensor gateway, work-order system, or physical-control integration.
- All live measurements, faults, rule alerts, and trained-baseline outputs in this API are synthetic/research artifacts, not validated industrial diagnoses, failure probabilities, or RUL predictions.
- IMS support is offline and local-file-only; no IMS data is served by this API.
