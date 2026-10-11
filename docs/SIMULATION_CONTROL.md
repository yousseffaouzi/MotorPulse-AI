# Simulation control — MP-017

This demo runs on **localhost only**, with no cloud, database, or third-party dependencies. The server owns a timed background worker and cached telemetry. Dashboard polling never advances the simulation.

## Lifecycle and HTTP endpoints

On startup, the seed is 42, tick 1 is generated, and the controller runs automatically at 1.5-second intervals.

- `GET /api/snapshot`: read the latest v1 telemetry; repeated GET requests never trigger a step.
- `GET /api/status`: JSON containing `state` (`running` or `paused`), `tick`, `seed`, `interval_seconds`.
- `POST /api/control`: JSON with exactly one `action`: `start`, `pause`, `step`, or `reset`.

**Start** resumes automatic ticks; **Pause** freezes them. **Step** advances exactly one tick, only while paused (409 otherwise). **Reset** pauses and generates tick 1 again from the original seed. Measurements are numerically repeatable but wall-clock timestamps are not: MP-018 will supply a virtual clock.

Send `Content-Type: application/json`. Invalid JSON/actions return HTTP 400, an unsupported media type returns 415, and a step during running returns 409. Bodies are limited to 4096 bytes. The controller uses a condition lock for consistent concurrent access and clean thread shutdown.

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
