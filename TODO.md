# MotorPulse AI — Master TODO & Development Roadmap

**Last updated:** 2026-10-11  
**Scope:** Open-source, software-first industrial motor condition monitoring and predictive-maintenance **simulation**. No hardware, PLC control, remote deployment, or operational maintenance decisions in this phase.

## v1 definition of done

From a fresh clone (Python 3.11+), a contributor can run a reproducible multi-motor simulator; configure healthy/fault/degradation scenarios; view live and historical time-stamped vibration, temperature and RPM features; export labelled synthetic data; ingest at least one properly documented public bearing dataset; evaluate leakage-resistant ML baselines against explainable threshold rules; and review results through a local dashboard. CI passes and a tagged demo release explains all limitations.

**Scientific caveat:** Current warnings are rule-based, not trained failure predictions. Synthetic scores are not calibrated failure probabilities; RUL and real-world industrial performance are not validated.

**Priority:** `P0` blocks core development; `P1` required for v1; `P2` enhancements; `P3` later scope.  
**Status:** `DONE` verified in repository; `TODO` not yet implemented; `IN PROGRESS` being worked on; `ON HOLD` deferred.

## Current baseline (2026-10-11)

- `motorpulse/sim.py`: deterministic configurable multi-motor simulator with time/spectral and rolling features, fault/sensor labels, and rule-based classifications.
- `motorpulse/__main__.py`: localhost-only `/api/snapshot`, `/api/status`, `/api/control`, `/api/health` API; GET no longer advances the simulator.
- `motorpulse/web/index.html`: packaged dashboard with Start/Pause/Step/Reset and scenario editor; persistent history remains pending.
- `tests/test_sim.py`, `tests/test_clock.py`, `tests/test_contracts.py` and `.github/workflows/test.yml`: simulator, deterministic replay, and API contract tests; PR-only/manual GitHub Actions.
- MP-006 implemented: telemetry v1 schema, UTC timestamps, event IDs, sampling metadata, canonical units and automated validation.
- MP-018 implemented: configurable virtual UTC epoch and tick spacing; identical configuration/seed/tick sequence reproduces complete snapshots, independent of wall clock.
- MP-019 implemented: 1024 Hz / 1024-sample waveform windows, RPM-linked 1×/2× signatures, illustrative 4.8× bearing impacts, and numerical spectral regression tests.
- MP-007 implemented: validated 1–12 motor scenarios with severity, onset/duration, browser editor, atomic configuration API, and deterministic replay; gradual degradation remains MP-020.
- MP-020 implemented: deterministic linear/exponential fault severity growth, phases, strict config validation, dashboard severity preview, and reset/replay tests.
- MP-021 implemented: 13 new localhost/API contract tests for JSON headers, error handling, malformed/oversized requests, concurrent stepping, replay, schema compatibility and dashboard smoke; 64 pre-packaging tests.
- MP-022 implemented: pyproject.toml and console script, a bundled dashboard asset, installation guide, four packaging tests, and an isolated offline wheel-build smoke check.
- MP-023 implemented: Hann-windowed radix-2 FFT, RPM-aware 1×/2× spectral peaks, high-frequency band RMS, per-motor 5-tick rolling averages, API/JSON-schema fields, and numerical regression tests.
- MP-024 implemented: local bounded JSON scenario loader, strict validation, `--config`/`--paused`/`--port` CLI flags, and nine file/startup regression tests.
- MP-025 implemented: deterministic operating variability, simulated noise/drift, sensor missing/outlier windows, explicit sensor quality, nullable vibration features, and 11 new tests.
- MP-026 implemented: canonical scientific model reference with equations, parameter tables, temporal/acquisition units, synthetic threshold caveats, methodological citations, doc corrections and seven regression checks.
- MP-008 implemented: bounded reproducible per-motor CSV/JSONL event export, seed/config/source SHA-256 provenance, data dictionary, null-handling, checksummed manifest, non-overwrite output and 12 export tests.
- MP-027 review completed: official IMS donor citation, download sources, NASA licensing caveat, source card and offline validation. **Raw-data and derivative redistribution permissions remain unverified and publication remains ON HOLD; no archive was downloaded or committed.**
- MP-009 implemented: bounded, no-network IMS-style local ASCII inspector, explicit rate/row/channel inputs, timestamp parsing, per-channel RMS/crest/peak-to-peak, local SHA-256 provenance, optional explicitly sourced bearing map, failure-onset/RUL nulls and 15 tests with entirely handwritten fixtures. **Not verified on the real source archive; original/derived data remain unpublishable under project policy.**
- MP-028 implemented: offline local IMS report integrity and chronology validation, checksum re-verification, unit/channel consistency, review-only quality flags, optional native-rate Hann tone amplitude, and run-disjoint training-only standardization (24 new tests). No verified field calibration, real-archive ingestion or redistribution rights claimed.
- MP-029 implemented: bounded, deterministic JSON/Markdown exploratory summaries for verified synthetic exports and local-only IMS inspection reports; numeric distributions, missingness, group trends, provenance, review flags and 18 regression tests. No IMS data, trained model or inferred failure labels are bundled.
- No trained AI model, persisted database, external ingestion adapter or real-hardware connection.

## Milestone 0 — Existing proof of concept

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| MP-001 | DONE | P0 | Publish initial architecture and constraints | README and architecture document available |
| MP-002 | DONE | P0 | Implement synthetic motor generator | Deterministic numeric readings for three motors |
| MP-003 | DONE | P0 | Add explainable rule-based scoring | Documented thresholds and unit tests |
| MP-004 | DONE | P0 | Expose localhost API and starter dashboard | python -m motorpulse; /api/snapshot and UI |
| MP-005 | DONE | P0 | Add unit tests and CI | unittest and GitHub Actions workflow |

**Exit criteria:** Baseline simulator, browser dashboard and CI work as documented.

## Milestone 1 — Reliable simulation platform

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| MP-006 | DONE | P0 | Define versioned telemetry, asset, sensor, feature and event schemas | schema_version, event_id, asset_id, UTC timestamp, units, source, scenario, sampling metadata, examples and validation tests |
| MP-007 | DONE | P0 | Configurable fault scenario library | Healthy, imbalance, bearing wear, misalignment, overload; severity and duration parameters; deterministic tests |
| MP-017 | DONE | P0 | Separate simulation progression from snapshot reads | GET snapshot is read-only; explicit step/start/pause/reset; integration tests |
| MP-018 | DONE | P0 | Reproducible simulated clock and replay | Same seed and configuration reproduce timestamps and measurements, independent of wall clock |
| MP-019 | DONE | P0 | Physically defined waveform sampling | Sampling rate in Hz, sample count, units, window duration; documented waveform assumptions |
| MP-020 | DONE | P0 | Progressive fault and degradation timelines | Configurable onset/growth across ticks; replayable healthy → degradation → alert transitions |
| MP-021 | DONE | P0 | API and simulator contract tests | Test payload shapes, invalid requests, concurrency, health and controls |
| MP-022 | DONE | P1 | Packaging and consistent developer commands | pyproject.toml, documented setup and CLI on supported Python versions |
| MP-023 | DONE | P1 | Extend signal-processing features | FFT/spectral and rolling features with reference numerical tests |
| MP-024 | DONE | P1 | Scenario and asset configuration | Validated JSON/YAML or CLI configuration without source edits |
| MP-025 | DONE | P1 | Operational variability and sensor problems | Speed/load variability, noise, missing values, drift and outliers with correct labels |
| MP-026 | DONE | P1 | Document simulation physics and assumptions | Equations, units, thresholds and limits; no unvalidated industrial standards claims |

**Exit criteria:** A replayable simulation produces time-stamped series with multiple configurable assets and progressive faults.

## Milestone 2 — Synthetic and external datasets

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| MP-008 | DONE | P1 | Export synthetic datasets | CSV/JSONL or Parquet CLI; metadata, seed, labels, dictionary, round-trip tests |
| MP-009 | DONE | P1 | NASA IMS bearing data ingestion | Load local data + small test fixtures; do not commit third-party raw archives |
| MP-027 | DONE | P1 | Dataset provenance and reuse review | Check citation, source, redistribution terms, checksum, acquisition date |
| MP-028 | DONE | P1 | Dataset validation and preprocessing | Channel mapping, frequencies, units, timestamps, NaN handling, corrupt-file tests |
| MP-029 | DONE | P1 | Exploratory data quality report | Reproducible distributions, trend examples, data quality and label caveats |
| MP-030 | TODO | P1 | Leakage-resistant train/validation/test splitting | Group by run/bearing/asset; preserve temporal order when required |
| MP-031 | TODO | P2 | Optional CWRU data adapter | Reuse terms and dataset card; distinguish seeded faults from run-to-failure |
| MP-032 | TODO | P1 | Dataset cards | Provenance, methods, limitations, intended use and licensing for synthetic and real data |

**Exit criteria:** Synthetic exports and one documented external dataset adapter work with leakage-resistant splitting.

## Milestone 3 — Defensible ML baselines

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| MP-010 | TODO | P1 | Classical ML baselines | Compare existing rules with healthy-trained anomaly detector; supervised baseline only if labels permit |
| MP-011 | TODO | P1 | Fault detection metrics | False alarms, precision/recall/PR-AUC where relevant, detection delay and lead time |
| MP-033 | TODO | P1 | Reproducible training/evaluation CLI | Seeded configuration, frozen dependencies, repeatable metrics and saved reports |
| MP-034 | TODO | P1 | Leakage-free feature pipelines | Preprocessing fitted on training only; overlapping-window and group split tests |
| MP-035 | TODO | P1 | Versioned model artifacts | Save/load with feature contract, config, dataset and training metadata |
| MP-036 | TODO | P1 | Robustness across operating regimes | Evaluate by fault type, speed, load, noise and dataset; no cross-domain overclaims |
| MP-037 | TODO | P1 | Side-by-side rules vs ML | Same input, separate outputs, explanations and false-positive examples |
| MP-038 | TODO | P2 | Calibrate anomaly thresholds | Validation-only selection with false-alarm tradeoffs; untouched test split |
| MP-039 | TODO | P2 | Consider RUL as separate research track | Define failure labels, censoring and metrics before any RUL claims |

**Exit criteria:** Reproducible rule-versus-ML benchmark with honest metrics and documented limitations.

## Milestone 4 — Persistent backend and dashboard

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| MP-012 | TODO | P1 | Persist telemetry and alerts in SQLite | Versioned migrations, restart and history integration tests |
| MP-013 | TODO | P1 | Trend charts, filtering and accessible UI | Motor/time selection, temperature and vibration trends; keyboard and responsive tests |
| MP-014 | TODO | P2 | Optional SSE/WebSocket streaming | Live events and reconnect tested; polling fallback |
| MP-040 | TODO | P1 | History and event REST endpoints | Paginated and filtered reads; documented errors and response schema |
| MP-041 | TODO | P1 | Simulation controls in UI | Start/pause/reset, seed, scenario, severity, speed; explicit simulated time |
| MP-042 | TODO | P1 | Explicit alert lifecycle | Transitions, deduplication, reasons, severity and persistence |
| MP-043 | TODO | P1 | API request validation and errors | Bounds, content types, stable response codes and safe failure modes |
| MP-044 | TODO | P2 | Export charts and reports | Download telemetry/evaluation reports labelled as simulation |

**Exit criteria:** A user can control a run, see history and compare model outputs without editing source code.

## Milestone 5 — Reproducibility, quality and release

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| MP-015 | TODO | P2 | Demo video and benchmark report | Dated metrics, reproducible commands and linked demo media |
| MP-045 | TODO | P1 | Expanded quality gates | Lint/format, dependency reviews, API and integration tests, supported Python matrix |
| MP-046 | TODO | P1 | Fresh-clone reproducibility test | Install, run, export and evaluate from written instructions |
| MP-047 | TODO | P1 | API/configuration/architecture documentation | Updated diagrams, schemas, CLI tutorial and troubleshooting |
| MP-048 | TODO | P1 | Model cards and failure modes | Source dataset, intended use, validation and limitations for each baseline |
| MP-049 | TODO | P1 | Secure local-first defaults | Localhost-only; validate file paths/inputs; no unsafe controls or industrial guarantees |
| MP-050 | TODO | P2 | Community and issue templates | Issue/PR templates, contributor instructions and beginner tasks |
| MP-051 | TODO | P2 | Tag a usable release | SemVer, CHANGELOG, reproducible demo and honest release caveats |
| MP-052 | TODO | P2 | Optional containerized quick start | Simple Dockerfile/Compose; native Python remains supported |
| MP-016 | ON HOLD | P3 | Real sensors, PLC, edge and remote deployment | Separate later phase after software evaluation and security approval |

**Exit criteria:** Fresh-clone setup and evaluation verified; tagged release and community documentation available.


## Dependencies / suggested order

1. `MP-006 → MP-017 → MP-018 → MP-019 → MP-021`: telemetry and deterministic runtime.
2. `MP-007 → MP-020 → MP-024 → MP-025 → MP-008`: reproducible scenarios and export.
3. `MP-012 → MP-040 → MP-041 → MP-013`: persistent end-to-end monitoring.
4. `MP-027 → MP-009 → MP-028 → MP-030 → MP-032`: documented public data.
5. `MP-023 → MP-034 → MP-010 → MP-011 → MP-033 → MP-037 → MP-048`: reproducible ML benchmark.
6. `MP-045 → MP-046 → MP-047 → MP-049 → MP-015 → MP-051`: release readiness.

Parallel work is possible after the telemetry/clock contract: UI prototypes, dataset provenance review, signal analysis, and documentation.

## Suggested first GitHub issues

- **MP-006 — Versioned telemetry schema:** stable event IDs, UTC timestamps, source/units/sample metadata, examples, validation.
- **MP-017 — Read-only snapshot:** GET does not advance; explicit controls; concurrency-safe tests.
- **MP-018 — Simulated clock:** repeatable timestamps across runs.
- **MP-019 — Sampling contract:** rate (Hz), duration (s), vibration acceleration units (g), waveform reference.
- **MP-007 — Fault scenarios:** user-configurable fault families, severity and seed.
- **MP-020 — Degradation timeline:** multi-tick gradual fault progression.

## Data sources and careful use

- NASA IMS bearings: https://data.nasa.gov/dataset/ims-bearings (check original redistribution/reuse terms before importing).
- NASA PCoE datasets: https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
- CWRU bearings: https://engineering.case.edu/bearingdatacenter/welcome (artificially seeded faults; not equivalent to run-to-failure).
- ISO 20816-1: https://www.iso.org/standard/63180.html (measurement context only; no endorsement of existing thresholds in acceleration g).

## GitHub management

Keep task identifiers stable. Suggested labels: `priority:P0`, `priority:P1`, `priority:P2`, `simulation`, `signals`, `api`, `data`, `ml`, `ui`, `tests`, `docs`, `security`. Each implementation issue should include dependency IDs, acceptance tests, documentation impact and evidence before marking `DONE`.
