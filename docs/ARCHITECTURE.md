# Architecture — MotorPulse AI

## Stage 0 (implemented)

A deterministic synthetic plant produces 3 motor snapshots. A pure Python feature function extracts RMS, peak-to-peak and crest factor from a short acceleration waveform. The demo classifier uses explicit thresholds and explanatory reasons. A localhost-only HTTP server exposes JSON and static UI. MP-017 introduces a thread-safe simulator controller with an independent timed worker, cached read-only snapshots, and Start/Pause/Step/Reset actions. Dashboard polling no longer advances the simulator. MP-018 now provides deterministic simulated UTC timestamps and replayable resets, independent of wall-clock scheduling. MP-019 adds a separately testable acceleration waveform generator, RPM-linked shaft harmonics, 1-second sampling windows, and synthetic fault impulses. MP-007 adds immutable validated per-asset scenarios, severity-scaled synthetic fault signatures, a scheduled onset/finite duration and an atomic in-memory configuration API. MP-020 adds deterministic configurable linear/exponential severity ramps, fault phase metadata and a configured trajectory preview in the dashboard. Persistent telemetry storage is not yet implemented. No persisted telemetry or trained model is implemented.

## Stage 1 (planned)

Introduce typed event schemas (`event_id`, `asset_id`, `timestamp_utc`, `scenario`, sensor samples and derived features), a scenario library, synthetic dataset export, and deterministic tests. Keep samples and aggregate features separately for efficiency and traceability.

## Stage 2 (planned)

Add ingestion adapters for public bearing datasets, non-leaky splits by run/asset, supervised and unsupervised baselines, reproducible evaluations and confidence/uncertainty reporting. Do not claim remaining useful life accuracy without validation.

## Stage 3 (planned)

Introduce SQLite persistence and streaming dashboard. Move from a single-process demo to a separately deployed API worker only when workload requires it. If Supabase is added, keep it optional rather than a precondition for contributors.

## Current non-goals

- No ESP32, Raspberry Pi, accelerometers or telemetry gateways.
- No production alarms or maintenance work-order automation.
- No cloud deployment, remote control or PLC communications.
- No claims that synthetic anomaly detection equals predictive maintenance.

## Security

Demo bound to `127.0.0.1` only. Do not port-forward. Authentication, authorization, rate limiting and audit trails are future prerequisites for any network-facing installation.
