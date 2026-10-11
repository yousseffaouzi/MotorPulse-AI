# Simulation control — MP-017

This demo runs on **localhost only**, with no cloud, database, or third-party dependencies. The server owns a timed background worker and cached telemetry. Dashboard polling never advances the simulation.

## Lifecycle and HTTP endpoints

On startup, the seed is 42, tick 1 is generated at virtual `2026-01-01T00:00:00+00:00`, and the controller runs automatically at 1.5-second **wall-clock** intervals. The virtual clock advances independently of the real timer.

- `GET /api/snapshot`: read the latest v1 telemetry; repeated GET requests never trigger a step.
- `GET /api/status`: JSON containing `state`, `tick`, `seed`, `interval_seconds` (wall scheduling), `step_seconds` (virtual advance), `start_time_utc`, and `simulated_at_utc`.
- `POST /api/control`: JSON with exactly one `action`: `start`, `pause`, `step`, or `reset`.

**Start** resumes automatic ticks; **Pause** freezes them. **Step** advances exactly one tick, only while paused (409 otherwise). **Reset** pauses and generates tick 1 again from the original seed. Both measurements and UTC timestamps are completely repeatable for the same seed, start time, step size, and tick sequence (MP-018). Tick 1 equals the chosen virtual start; subsequent ticks advance by the virtual step size. The worker's actual wall-clock delay does not alter those readings.

Send `Content-Type: application/json`. Invalid JSON/actions return HTTP 400, an unsupported media type returns 415, and a step during running returns 409. Bodies are limited to 4096 bytes. The controller uses a condition lock for consistent concurrent access and clean thread shutdown.

## Configurable virtual time

```bash
python -m motorpulse --seed 42 --start-time-utc 2026-01-01T00:00:00Z --step-seconds 2 --interval-seconds 0.5
```

`--start-time-utc` must be an explicit UTC ISO 8601 instant (Z or +00:00), `--step-seconds` must be positive with whole-microsecond precision, and `--interval-seconds` is the real time between automatic ticks. The example produces simulated timestamps 00:00:00, 00:00:02, 00:00:04, … while stepping every 0.5 real seconds. The fixed step may differ from the signal sampling window of 1.0 second; if virtual steps are shorter, the modeled windows overlap in timestamp terms but are independently generated (no continuous physical phase model). MP-019 documents this approximation.

## Demo

```bash
python -m motorpulse
# in another terminal:
curl http://127.0.0.1:8765/api/status
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"pause"}'
curl http://127.0.0.1:8765/api/snapshot
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"step"}'
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"reset"}'
```

Run `python -m unittest discover -s tests -v` for controller, concurrency and HTTP integration tests. The browser dashboard also provides the control buttons.

**Safety:** this standard-library HTTP server is not production-ready. Do not expose the server to the public internet, attach to machinery, or act on its simulated maintenance alerts.
