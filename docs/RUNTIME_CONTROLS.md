# MP-041 — Browser simulation seed and clock controls

MotorPulse AI is a reproducible **synthetic-only** condition-monitoring lab. The dashboard now exposes the simulator seed and two deliberately separate clocks, alongside the existing per-motor scenario, severity, simulated RPM variability, load variability, noise and progression editor. The UI is not connected to a physical drive, motor speed regulator, live sensors or PLC.

## Using the dashboard

Start the local server:

    python -m motorpulse --paused
    # or persist source sessions:
    python -m motorpulse --paused --database ./motorpulse-local.sqlite3

The top of the dashboard includes Start, Pause, Step +1 and Reset. The Simulation seed and time form provides:

| Field | Domain | Meaning |
| --- | --- | --- |
| Deterministic seed | Integer 0 to 2147483647 | Chooses deterministic pseudo-random generator sequence for each motor/tick; the same settings produce the same synthetic features |
| Virtual clock (seconds per tick) | 0.000001 to 86400, whole microseconds | Interval between labelled virtual timestamps. Each vibration window remains 1024 samples at 1024 Hz (1.0 s nominal window), independent of virtual tick spacing |
| Real update interval (wall seconds) | 0.05 to 3600 | Requested **wall-clock** delay between automatic steps when Start is active; elapsed wall-clock time may vary with process scheduling and compute load |

Apply simulation settings pauses the controller and resets the recording to tick 1, **preserving the configured motors and virtual UTC epoch**. Reset (without applying) replays the current seed and clocks. Changes during a running simulation pause it; Step remains unavailable until paused.

The Fault scenarios editor continues to expose: synthetic fault family, strength from 0 to 1, onset, optional finite duration, constant/linear/exponential trajectory, ramp, and independent speed/load variability and noise/drift. **Speed variability 0–0.2 means ±0–20% variation around the simulator's approximate 1480 RPM synthetic base, not a controllable real motor RPM setpoint.** Changes to any asset configuration pause/reset and preserve seed and timing.

Active seed, simulated seconds per tick, wall update interval, virtual tick and UTC timestamp are shown explicitly. Accessibility uses programmatically associated numeric labels, native input constraints, focus styling, a responsive layout and polite live status/error messages. Unsaved edits are **not overwritten by periodic status polling**; server-reported values are synced after a successful Apply. A paused simulator's GET /api/snapshot does not create ticks.

If SQLite persistence was enabled via --database, each successful application creates an independent source session with the updated seed/step interval; old sessions and deterministic original event IDs survive under separate session UUIDs. Startup and runtime updates do **not** recover the previous running state. No database is created in the default in-memory mode.

## API contract: PUT /api/runtime

The localhost-only HTTP endpoint accepts an exact JSON document with all three fields:

    PUT /api/runtime
    Content-Type: application/json

    {
      "seed": 1357,
      "step_seconds": 0.5,
      "interval_seconds": 1.5
    }

The response on success is HTTP 200 and the same shape as GET /api/status, including updated seed, tick=1, state=paused, virtual start timestamp, virtual step and real interval. With SQLite enabled, status also includes storage and the **new session_id**. There is no GET /api/runtime: read current settings through GET /api/status.

Strict validation rejects extra/missing fields; boolean/string/float seed; negative/oversized seed; nonfinite/boolean timing values; sub-microsecond virtual steps that cannot be represented exactly; out-of-range wall cadence. Invalid input returns HTTP 400 with an error object. Closed or persistence-error controllers reject updates with HTTP 409. Synchronous SQLite persistence failures return HTTP 503 without claiming the runtime settings were committed. Unrecognized routes or methods remain 404; unsupported media types return 415. All existing snapshot/config/control responses remain compatible.

### Atomic restart guarantee

The candidate simulator, seed and new initial snapshot are validated before any memory mutation. With persistence enabled, the full initial snapshot and the new session row are written in **one SQLite transaction**. Only after this succeeds do the seed, cadence, simulator, current snapshot and session identity change. A database failure leaves the previous live runtime untouched. Updating settings while running pauses background stepping and resets to virtual tick 1 in one synchronized controller operation.

These seeds and timestamps are for reproducible educational experiments. There are **no industrial severity thresholds, guaranteed temporal accuracy, failure probabilities, remotely operable hardware, calibrated faults or Remaining Useful Life estimates**.

## Reproduce tests

    python -m unittest discover -s tests -p 'test_runtime_controls.py' -v
    python -m unittest discover -s tests -v

The MP-041 tests cover deterministic seed/clock replay, valid and invalid types/ranges, submicrosecond rejection, background worker pause, scenario preservation, SQLite new-session persistence and rollback, exact localhost PUT response/errors and semantic dashboard hooks/focus/mobile styling. The full test suite is dependency-free. MP-013 charts/history UI and MP-042 alert lifecycle remain separate roadmap work.
