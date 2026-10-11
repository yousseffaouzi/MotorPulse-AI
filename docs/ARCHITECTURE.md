# Architecture — MotorPulse AI

## Stage 0 (implemented)

A deterministic synthetic plant starts with three configured motor assets and generates one 1024-sample, 1024 Hz synthetic acceleration window per asset on each virtual tick. Standard-library feature functions produce time- and frequency-domain summaries, with explicit sensor-quality status and non-ML health rules. The demo classifier uses explicit thresholds and explanatory reasons. A localhost-only HTTP server exposes JSON and static UI. MP-017 introduces a thread-safe simulator controller with an independent timed worker, cached read-only snapshots, and Start/Pause/Step/Reset actions. Dashboard polling no longer advances the simulator. MP-018 now provides deterministic simulated UTC timestamps and replayable resets, independent of wall-clock scheduling. MP-019 adds a separately testable acceleration waveform generator, RPM-linked shaft harmonics, 1-second sampling windows, and synthetic fault impulses. MP-007 adds immutable validated per-asset scenarios, severity-scaled synthetic fault signatures, a scheduled onset/finite duration and an atomic in-memory configuration API. MP-020 adds deterministic configurable linear/exponential severity ramps, fault phase metadata and a configured trajectory preview in the dashboard. Persistent telemetry storage is not yet implemented. MP-022 now packages the flat-layout Python modules and `motorpulse/web/index.html` in a setuptools wheel; the localhost HTTP server loads its dashboard relative to the installed module location. MP-023 adds a pure-Python FFT spectral feature stage and in-memory per-asset five-tick rolling means. MP-024 adds a bounded UTF-8 JSON startup loader that validates motor scenarios before opening a localhost socket, and CLI controls for paused startup/port selection. It uses the same `parse_configuration` contract as the in-memory API. MP-025 adds seeded operational speed/load variability and sensor-quality events to the same per-asset configuration. Missing/outlier vibration blocks normal machine assessment while keeping ground-truth machine fault labels separate. The API reads only the current cached features and does not persist waveforms or telemetry. The offline MP-008 export CLI independently replays the same simulated ticks to generate files; it is not a database or part of the running HTTP server. MP-026 consolidates model equations, numeric coefficients, physical units, and non-goals in [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md). No persisted telemetry or trained model is implemented.

## Stage 1 (planned)

The v1 JSON snapshot/event feature schema and deterministic scenario library already exist. MP-008 now provides **CSV/JSONL synthetic feature-event export**, a source/config-hashed reproducible export identity, validated tick bounds, safe new-directory writes, and per-file SHA-256 provenance. Raw waveform export and globally unique run/session IDs remain separate work. MP-027 has completed the **metadata-level** IMS provenance and licensing review in [DATA_PROVENANCE.md](DATA_PROVENANCE.md); **dataset-specific redistribution and derivative rights remain unresolved**, and original/processed third-party data must not be bundled. See [DATASET.md](DATASET.md). Keep samples and aggregate features separately for efficiency and traceability.

## Stage 2 (planned)

MP-009 now provides a **bounded local-only IMS-style ASCII inspector** operating on user-supplied, already-extracted files, preserving test-set/run/channel/timestamp keys and leaving unverified bearing mapping, timezone, physical units, onset and RUL unknown. It is not connected to the synthetic classifier or live HTTP server. See [IMS_INGESTION.md](IMS_INGESTION.md). Next steps: MP-028 rigorous dataset validation/preprocessing and later non-leaky splits by run/asset, supervised and unsupervised baselines, reproducible evaluations and uncertainty reporting. Never assume IMS waveforms use the synthetic 1024 Hz schema. No upstream archive or derived waveforms may be committed until rights are verified. Do not claim remaining useful life accuracy without validation.

## Stage 3 (planned)

Introduce SQLite persistence and streaming dashboard. Move from a single-process demo to a separately deployed API worker only when workload requires it. If Supabase is added, keep it optional rather than a precondition for contributors.

## Current non-goals

- No ESP32, Raspberry Pi, accelerometers or telemetry gateways.
- No production alarms or maintenance work-order automation.
- No cloud deployment, remote control or PLC communications.
- No claims that synthetic anomaly detection equals predictive maintenance.

## Security

Demo bound to `127.0.0.1` only. Do not port-forward. Authentication, authorization, rate limiting and audit trails are future prerequisites for any network-facing installation.
