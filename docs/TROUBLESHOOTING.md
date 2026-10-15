# MotorPulse AI troubleshooting

This guide covers the **local synthetic research lab**. MotorPulse AI has no supported public-network deployment, real-sensor connection, PLC integration, or physical motor control. **No real sensors** or machinery should be connected while following these steps.

## The server will not start on port 8765

The default listener is `127.0.0.1:8765`. If another process already owns **port 8765**, choose another loopback port:

```bash
python -m motorpulse --paused --port 8766
```

For automated local tests, `--port 0` asks the OS for a temporary loopback port and the app prints the selected address. The host itself is intentionally fixed to `127.0.0.1`; there is no supported `0.0.0.0` mode.

If the process exits with an `argparse` error, fix the reported startup argument/configuration problem first. Startup validation happens before the normal serving loop.

## `motorpulse-ai` or another console command is not found

Activate the same virtual environment where you installed the project:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
motorpulse-ai --help
```

You can always test the source entry point from the repository root with `python -m motorpulse --help`. The MP-046 acceptance harness, `python scripts/fresh_clone_smoke.py`, creates a separate temporary virtual environment and verifies installed commands from outside the checkout.

If build isolation cannot obtain setuptools/wheel, read [INSTALL.md](INSTALL.md) for the documented `--no-build-isolation` option when suitable build tools are already installed locally. Runtime dependencies remain empty.

## A startup JSON configuration is rejected

`--config FILE` expects a trusted local UTF-8 JSON file of **1–65,536 bytes** containing exactly the asset-configuration schema accepted by `PUT /api/config`. Common causes are:

- wrong current working directory for a relative path;
- empty, oversized, or non-UTF-8 files;
- duplicate JSON object keys;
- `NaN` / `Infinity` constants;
- unknown fields, duplicate asset IDs, invalid types or out-of-range scenario/operation settings.

Run with a known example:

```bash
python -m motorpulse --config docs/examples/scenarios-progressive.json --paused
```

See [CONFIG_FILE.md](CONFIG_FILE.md), [SCENARIOS.md](SCENARIOS.md), [PROGRESSION.md](PROGRESSION.md), and [OPERATIONS.md](OPERATIONS.md).

## An API request returns 400, 411, 413, or 415

For JSON mutation endpoints, use an explicit JSON media type and let your HTTP client provide a valid `Content-Length`:

```bash
curl -X POST http://127.0.0.1:8765/api/control \
  -H 'Content-Type: application/json' \
  -d '{"action":"pause"}'
```

The HTTP body boundary is separate from the startup-file boundary: JSON request bodies are limited to **16,384 bytes**, maximum parsed nesting is 64, duplicate keys and non-standard numeric constants are rejected, and an empty body is invalid.

Use the response `code` rather than matching the human-readable `error` string. Common framing/parser cases are:

| HTTP | Code | Check |
| --- | --- | --- |
| 400 | `invalid_json` | UTF-8/JSON syntax, duplicate keys, non-standard constants, nesting |
| 411 | `length_required` | Missing/malformed `Content-Length` |
| 413 | `invalid_request_size` | Empty or body larger than 16,384 bytes |
| 415 | `unsupported_media_type` | Missing/wrong `Content-Type` |

Endpoint-specific validation also uses HTTP **400**, for example `invalid_configuration`, `invalid_runtime_settings`, `invalid_control_request`, `invalid_history_query`, or `invalid_acknowledgement`. See [API.md](API.md).

## An API request returns 409

HTTP **409** means the request is structurally valid but cannot be applied in the current local state.

Common examples:

- `control_conflict`: trying to step while the simulator is running, changing a closed controller, or another state conflict;
- `history_unavailable`: history/incident access was requested but the app was not started with `--database`;
- `incident_already_acknowledged`: the once-only local review marker already exists.

Pause the simulator before `step`. For optional history, restart with an explicit local path:

```bash
python -m motorpulse --paused --database ./motorpulse-local.sqlite3
```

A database-backed reset/config/runtime change creates a distinct recording session; it does not resume a previous running session.

## An API request returns 503

HTTP **503** represents a local SQLite/storage failure while persistence is required. Mutation failures use `persistence_unavailable`; history/incident storage reads or review writes use `history_storage_error`.

Checks:

1. Confirm the directory containing the `--database` path exists and is writable by the current user.
2. Confirm the path is a normal local SQLite file location and not a directory.
3. Make sure another tool is not holding an incompatible lock or replacing/corrupting the file.
4. If the file matters, copy/back it up before manual recovery attempts.
5. Restart without `--database` only if you intentionally accept in-memory-only operation and do not need history/incidents.

MotorPulse AI does not expose raw SQL errors or local filesystem paths through API 503 responses. A failed transactional tick/config/runtime change does not publish an in-memory state that falsely claims persistence succeeded.

## History queries return `invalid_history_query`

History query parsing is intentionally strict. Do not send unknown or duplicate parameters, padded/empty values, malformed percent escapes, more than the supported fields, or a `limit` outside 1–100. Use `before_id` for newest-first pagination. Time filters must be exact supported UTC values and `start_utc` must not exceed `end_utc`.

Resource-specific filters are documented in [HISTORY_API.md](HISTORY_API.md) and summarized in [API.md](API.md).

## An output file or directory already exists

Offline research commands generally avoid silent overwrite. A previous run can therefore cause a deliberate failure when the requested output path already exists.

Prefer a new output path:

```bash
motorpulse-export --out-dir datasets/run-44 --ticks 30 --seed 44 --format jsonl
```

Only delete/rename previous local artifacts after deciding you no longer need their provenance. Do not work around checksum/source-identity errors by editing manifests or model artifacts; rerun the upstream step with the intended inputs instead.

## A model/split/evaluation rejects provenance

This is usually a safety feature rather than a parser bug. Downstream tools bind to source manifests, whole-run split identities, dataset cards, preprocessing/model hashes, and partition roles. Changed/missing source files, a mismatched split, or a model trained from different sources must be rejected.

Recreate the chain from known inputs instead of disabling validation. The recommended synthetic sequence is in [CLI.md](CLI.md): export → whole-run split → healthy-only training → held-out evaluation.

## IMS commands reject files or metadata

IMS support is **local-file-only**. The project does not download or bundle the NASA IMS archive. Do not assume the synthetic 1024 Hz schema, units, labels, timezone, bearing mapping, fault onset, or RUL for IMS files.

Provide the required local metadata and consult [IMS_INGESTION.md](IMS_INGESTION.md), [IMS_VALIDATION.md](IMS_VALIDATION.md), and [DATA_PROVENANCE.md](DATA_PROVENANCE.md). Redistribution/derivative rights for third-party data remain a separate review concern.

## Browser shows stale or unavailable history

Live snapshot/status polling and historical SQLite reads are different paths. If history is unavailable, confirm the server was launched with `--database`. If you changed configuration/runtime settings or reset, select the correct recording session: those operations intentionally create independent session UUIDs with persistence enabled.

The browser does not read SQLite directly. It uses the bounded localhost history API. See [HISTORICAL_DASHBOARD.md](HISTORICAL_DASHBOARD.md).

## Unknown API path or method returns 404

This is expected. Unknown `/api/...` paths and unsupported API `DELETE`, `PATCH`, or `OPTIONS` requests return JSON 404 with `unknown_api_endpoint`. API `HEAD` also returns that 404 contract with no response body. Cross-origin CORS preflight is not enabled.

Use only the methods/paths listed in [API.md](API.md).

## Safety boundary

If troubleshooting seems to require any of the following, stop: exposing the server publicly, forwarding the local port, attaching a sensor/PLC/actuator, treating synthetic rule incidents as physical alarms, or using synthetic/IMS exploratory outputs as validated failure probability or RUL. Those are outside the supported project scope.
