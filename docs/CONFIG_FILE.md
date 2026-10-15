# Local and HTTP configuration — MotorPulse AI

MotorPulse AI supports reproducible **synthetic motor** scenarios loaded either from a strict local JSON file before startup or through the localhost asset-configuration API while the process is running. Both use the same validated `{ "assets": [...] }` schema. A separate runtime API controls the deterministic seed and clocks.

No configuration mechanism controls physical equipment, downloads remote content, evaluates code, or writes back to the startup JSON file.

## Three configuration surfaces

| Surface | Purpose | Limit / boundary | Mutation timing |
| --- | --- | --- | --- |
| `--config FILE` | Load all asset/scenario settings from a trusted local file | UTF-8 JSON, **1–65,536 bytes** | Before the server socket opens |
| `PUT /api/config` | Replace all active asset/scenario settings | HTTP JSON body, **1–16,384 bytes** | Runtime; pauses and resets after validation |
| `PUT /api/runtime` | Replace seed, virtual tick step and real worker interval | HTTP JSON body, **1–16,384 bytes** | Runtime; pauses and resets after validation |

The local file and `PUT /api/config` deliberately share the same scenario parser. `PUT /api/runtime` is a different schema and does not accept asset fields.

## Quick start from a local file

From the repository root:

```bash
python -m motorpulse --config docs/examples/scenarios-progressive.json --paused
```

Use the browser at `http://127.0.0.1:8765`, or inspect `GET /api/config` and `GET /api/snapshot`. The simulator begins **paused at tick 1**, so repeated snapshot reads return the same initial data. Click Step or use `POST /api/control` to advance the synthetic timeline.

A replayable custom clock and port:

```bash
python -m motorpulse \
  --config docs/examples/scenarios-progressive.json \
  --seed 72 --start-time-utc 2026-05-20T12:00:00Z \
  --step-seconds 2.5 --interval-seconds 0.5 \
  --paused --port 8766
```

The installed `motorpulse-ai` CLI supports the same options. `--port 0` binds to an available **loopback** port and prints the actual port, convenient for local integration tests. The host stays fixed to `127.0.0.1`; `--port` does **not** expose the app externally.

## Asset JSON schema

The accepted startup-file format is exactly the body used by `PUT /api/config`: one top-level `assets` array containing **1–12** distinct motors.

```json
{
  "assets": [
    {"asset_id":"MTR-01","name":"Conveyor","scenario":"healthy","severity":0},
    {"asset_id":"MTR-02","name":"Pump","scenario":"imbalance","severity":0.8,"onset_tick":3,"progression":"linear","start_severity":0,"ramp_ticks":10},
    {"asset_id":"MTR-03","name":"Fan","scenario":"bearing_wear","severity":1,"onset_tick":5,"duration_ticks":24,"progression":"exponential","start_severity":0.05,"ramp_ticks":12}
  ]
}
```

Fault/scenario fields, validation ranges, progression equations and synthetic assumptions are defined in [SCENARIOS.md](SCENARIOS.md) and [PROGRESSION.md](PROGRESSION.md). Operating/sensor variability is in [OPERATIONS.md](OPERATIONS.md); `docs/examples/operations-v1.json` is a reproducible example. Optional fields use the canonical scenario defaults. The loader returns the same immutable `AssetScenario` values used by the running controller; it does not implement a second schema.

### Local-file boundary: `--config`

The startup loader in `motorpulse/config_file.py` is intentionally bounded and strict:

- `--config FILE` accepts a **local UTF-8 JSON regular file**.
- Relative paths resolve from the current shell working directory, not the installed package location.
- File length must be **1–65,536 bytes**. The reader consumes at most 65,537 bytes before rejecting an oversized file.
- Empty files, invalid UTF-8, malformed JSON, **duplicate** object keys at any nesting level, `NaN`/`Infinity` tokens, unsupported fields, duplicate motor IDs and invalid scenario/operation values are rejected.
- Bad configuration or CLI arguments produce an `argparse` error and exit code 2 before the normal server loop opens.
- The loader does not fetch URLs, parse YAML, evaluate expressions, unpickle objects, or perform implicit filesystem writes.
- After startup, the configuration exists in memory; the original file is never rewritten. Reset replays the current in-memory config, which may have changed through the API.

Use local files from a trusted source. Strict JSON parsing reduces ambiguity; it is not a sandbox for untrusted local filesystem access.

## Runtime asset replacement: `PUT /api/config`

The localhost endpoint accepts the same `{ "assets": [...] }` object but has the HTTP request boundary from MP-043:

```bash
curl -X PUT http://127.0.0.1:8765/api/config \
  -H 'Content-Type: application/json' \
  --data-binary @docs/examples/scenarios-progressive.json
```

Important differences from `--config FILE`:

- HTTP JSON bodies must be positive and no larger than **16,384 bytes**.
- `Content-Type: application/json` and a valid decimal `Content-Length` are required.
- Duplicate keys, non-standard JSON constants and invalid UTF-8 are rejected.
- Parsed JSON nesting depth is capped at 64.
- Invalid asset data returns HTTP 400 with `code="invalid_configuration"`.
- A controller-state conflict returns 409 `control_conflict`.
- A required SQLite commit failure returns 503 `persistence_unavailable` without publishing the candidate configuration as live.

A successful change pauses the controller and creates tick 1 from the new complete asset configuration while preserving the current runtime seed, clock settings and virtual UTC epoch. With optional SQLite persistence enabled, a new source session/initial snapshot is committed before the controller publishes the new in-memory state.

The complete framing/error contract is in [API.md](API.md).

## Runtime seed and clocks: `PUT /api/runtime`

Seed/timing configuration is intentionally separate from asset configuration. The body must contain exactly:

```json
{
  "seed": 1357,
  "step_seconds": 0.5,
  "interval_seconds": 1.5
}
```

`PUT /api/runtime` changes the deterministic random seed, virtual seconds per tick and real wall-clock worker interval. It preserves the configured assets and virtual start epoch, pauses the controller, and resets to tick 1. There is no `GET /api/runtime`; read the active values from `GET /api/status`.

Detailed numeric ranges, whole-microsecond timing requirements and transactional restart guarantees are in [RUNTIME_CONTROLS.md](RUNTIME_CONTROLS.md). Invalid data uses 400 `invalid_runtime_settings`; controller/persistence failures use the same 409/503 semantics as other atomic mutations.

## Startup CLI options versus runtime APIs

`--seed`, `--start-time-utc`, `--step-seconds`, `--interval-seconds`, `--database`, `--paused`, and `--port` are process startup options. Only seed/step/interval can later be replaced together through `PUT /api/runtime`; the virtual start epoch, database path, host binding and TCP port are not runtime-editable API settings.

`--start-time-utc` must be an explicit supported UTC instant. `--paused` starts at the first virtual timestamp without automatic progression. `--database PATH.sqlite3` opts into local persistence/history/incidents. Without `--database`, no SQLite database is created.

## Schema and source-of-truth map

- `motorpulse/scenarios.py` — canonical asset/scenario validation used by file/API config.
- `motorpulse/config_file.py` — bounded local JSON reader; no second scenario schema.
- `motorpulse/controller.py` — atomic configuration/runtime application and persistence-before-publication behavior.
- `motorpulse/__main__.py` — CLI startup flags plus strict localhost HTTP boundary.
- [SCENARIOS.md](SCENARIOS.md) — asset/fault semantics and core ranges.
- [PROGRESSION.md](PROGRESSION.md) — synthetic severity trajectories.
- [OPERATIONS.md](OPERATIONS.md) — speed/load/noise/missing/outlier sensor configuration.
- [RUNTIME_CONTROLS.md](RUNTIME_CONTROLS.md) — seed/clock API contract.
- [API.md](API.md) — consolidated HTTP methods, limits and machine-readable errors.

## Reproduce tests

```bash
python -m unittest discover -s tests -p 'test_config_file.py' -v
python -m unittest discover -s tests -p 'test_api_validation.py' -v
python -m unittest discover -s tests -p 'test_runtime_controls.py' -v
python -m unittest discover -s tests -v
```

These are educational simulation configuration surfaces, not production motor-control settings or network deployment interfaces.
