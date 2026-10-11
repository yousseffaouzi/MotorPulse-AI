# MP-024 — Start MotorPulse AI from a local JSON configuration

MotorPulse AI supports reproducible **synthetic motor** scenarios loaded before the HTTP server starts. No files are written or updated by this feature. The app remains localhost-only and cannot control machinery.

## Quick start

From the repository root:

```bash
python -m motorpulse --config docs/examples/scenarios-progressive.json --paused
```

Use the browser at `http://127.0.0.1:8765`, or inspect `GET /api/config` and `GET /api/snapshot`. The simulator begins **paused at tick 1**, so repeated snapshot reads return the same initial data. Click Step to advance the fault timelines.

A replayable custom clock and port:

```bash
python -m motorpulse \
  --config docs/examples/scenarios-progressive.json \
  --seed 72 --start-time-utc 2026-05-20T12:00:00Z \
  --step-seconds 2.5 --interval-seconds 0.5 \
  --paused --port 8766
```

The installed `motorpulse-ai` CLI supports the same options. `--port 0` binds to an available **loopback** port and prints the actual port, convenient for local integration tests. The host address stays fixed to `127.0.0.1`; `--port` does **not** expose the app externally.

## JSON format

The accepted file format is exactly the body used by `PUT /api/config`: one top-level `assets` array, containing **1–12** distinct motors. This example defines healthy, linear imbalance and exponential bearing-degradation conditions:

```json
{
  "assets": [
    {"asset_id":"MTR-01","name":"Conveyor","scenario":"healthy","severity":0},
    {"asset_id":"MTR-02","name":"Pump","scenario":"imbalance","severity":0.8,"onset_tick":3,"progression":"linear","start_severity":0,"ramp_ticks":10},
    {"asset_id":"MTR-03","name":"Fan","scenario":"bearing_wear","severity":1,"onset_tick":5,"duration_ticks":24,"progression":"exponential","start_severity":0.05,"ramp_ticks":12}
  ]
}
```

Details, validation ranges and synthetic assumptions are in [SCENARIOS.md](SCENARIOS.md) and [PROGRESSION.md](PROGRESSION.md). Unspecified optional fields use the existing scenario defaults, preserving compatibility with earlier JSON examples. The loader returns the project's immutable `AssetScenario` values; it does not implement a second configuration schema.

## File path and error semantics

- `--config FILE` accepts a **local UTF-8 JSON file**. A relative path is resolved from the **current shell working directory**, not from the package installation location.
- File length must be **1–65,536 bytes**. The reader only loads 65,537 bytes maximum before rejecting an oversized file.
- Missing files, directories, malformed JSON, duplicate keys at any nesting level, `NaN`/`Infinity` tokens, invalid Unicode, unsupported fields, duplicate motor IDs and invalid fault/ramp parameters are rejected.
- Bad configuration and CLI arguments result in an explanatory `argparse` error and **exit code 2 before opening the server socket**. A port-binding or OS error is reported similarly.
- `--seed`, `--start-time-utc`, `--step-seconds` and `--interval-seconds` still work. `--paused` starts at the first virtual timestamp with no automatic progression. Without it, the server starts automatically as before.
- The configuration is **in-memory only** after startup. `PUT /api/config` can still replace it while the server is running; no file writeback occurs. Reset replays the current in-memory config, not necessarily the original file.
- File content must come from a trusted local source. The loader does not execute expressions, evaluate YAML, download URLs, or deserialize pickles; the standard library JSON decoder and existing scenario validator are used.

## Local tests

```bash
python -m unittest discover -s tests -p 'test_config_file.py' -v
python -m unittest discover -s tests -v
```

The nine dedicated tests cover accepted sample files, round-trip scenarios, malformed/oversized files, duplicate keys, invalid fault parameters, CLI help/failures, and a pair of real subprocess server launches. The subprocess test uses `--port 0`, an isolated working directory, and `--paused` to verify snapshots and virtual timestamps reproduce across restarts without consuming GitHub Actions minutes.

This is for educational simulation, not production monitoring or network deployment.
