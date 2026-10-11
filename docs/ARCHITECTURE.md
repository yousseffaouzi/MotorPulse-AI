# Architecture — MotorPulse AI

## Stage 0 (implemented)

A deterministic synthetic plant starts with three configured motor assets and generates one 1024-sample, 1024 Hz synthetic acceleration window per asset on each virtual tick. Standard-library feature functions produce time- and frequency-domain summaries, with explicit sensor-quality status and non-ML health rules. The demo classifier uses explicit thresholds and explanatory reasons. A localhost-only HTTP server exposes JSON and static UI. MP-017 introduces a thread-safe simulator controller with an independent timed worker, cached read-only snapshots, and Start/Pause/Step/Reset actions. Dashboard polling no longer advances the simulator. MP-018 now provides deterministic simulated UTC timestamps and replayable resets, independent of wall-clock scheduling. MP-019 adds a separately testable acceleration waveform generator, RPM-linked shaft harmonics, 1-second sampling windows, and synthetic fault impulses. MP-007 adds immutable validated per-asset scenarios, severity-scaled synthetic fault signatures, a scheduled onset/finite duration and an atomic in-memory configuration API. MP-020 adds deterministic configurable linear/exponential severity ramps, fault phase metadata and a configured trajectory preview in the dashboard. Persistent telemetry storage is not yet implemented. MP-022 now packages the flat-layout Python modules and `motorpulse/web/index.html` in a setuptools wheel; the localhost HTTP server loads its dashboard relative to the installed module location. MP-023 adds a pure-Python FFT spectral feature stage and in-memory per-asset five-tick rolling means. MP-024 adds a bounded UTF-8 JSON startup loader that validates motor scenarios before opening a localhost socket, and CLI controls for paused startup/port selection. It uses the same `parse_configuration` contract as the in-memory API. MP-025 adds seeded operational speed/load variability and sensor-quality events to the same per-asset configuration. Missing/outlier vibration blocks normal machine assessment while keeping ground-truth machine fault labels separate. The API reads only the current cached features; it does not persist waveforms or telemetry. MP-026 consolidates model equations, numeric coefficients, physical units, and non-goals in [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md). No persisted telemetry or trained model is implemented.

## Stage 1 (planned)

The v1 JSON snapshot/event feature schema and deterministic scenario library already exist. The next stage is **synthetic CSV/JSONL export** with explicit provenance, seeds, labels, units and validation; raw waveform export and durable run/session IDs remain separate design work. Keep samples and aggregate features separately for efficiency and traceability.

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
