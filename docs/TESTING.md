# MotorPulse AI — Local testing and contract coverage (MP-021)

MotorPulse AI is a **software-only industrial motor simulation**, not a trained predictive-maintenance service or production control system. These regression tests verify software behavior, not accuracy on physical motors.

## Run locally

From the repository root, using Python 3.11 or later and **no third-party packages**:

```bash
python -m unittest discover -s tests -v
```

The suite contains **514 standard-library unittest test cases** (64 through MP-021, 4 packaging smoke tests from MP-022, 13 spectral/rolling checks from MP-023, 9 JSON/CLI startup tests from MP-024, 11 sensor/operating tests from MP-025, 7 model-reference regression tests from MP-026, 12 export/manifest regression tests from MP-008, 10 offline source-card/provenance checks from MP-027, 15 offline local IMS-style parser tests from MP-009, 18 IMS report/normalization tests and 6 native-tone tests from MP-028, 18 exploratory report/CLI regression tests from MP-029, 16 whole-run/chronological split tests from MP-030, 16 dataset-card/provenance/CLI tests from MP-032, 19 trained-anomaly/sensor-gating/split-leakage tests from MP-010, 21 held-out detection/report tests from MP-011, 16 reproducible experiment/CLI tests from MP-033, 19 feature/temporal-leakage tests from MP-034, and 19 portable model-artifact/integrity/CLI tests from MP-035, and 8 robustness-stress/provenance/output tests from MP-036, and 13 comparison/explanation/integrity/CLI tests from MP-037, and 13 validation-calibration/ties/leakage/CLI tests from MP-038, and 18 RUL evidence/censoring/asset-leakage/audit CLI tests from MP-039, and 19 SQLite session/migration/restart/atomicity/HTTP tests from MP-012, and 21 historical REST/UTC/pagination/error tests from MP-040, and 13 runtime seed/dual-clock/UI atomicity tests from MP-041, and 16 history chart/SQLite/frontend rendering tests from MP-013, 24 synthetic incident lifecycle/migration/review/UI tests from MP-042, 6 API validation/error/rollback tests from MP-043, 2 dependency-policy tests from MP-045, 5 documentation-contract tests from MP-047, 5 model-card documentation tests from MP-048, 6 local-first security tests from MP-049, 4 dated benchmark/demo tests from MP-015, 6 community/onboarding contract tests from MP-050, 6 bounded dashboard-export tests from MP-044, 6 localhost SSE/reconnect/fallback tests from MP-014, and 10 local-only CWRU MAT/parser/provenance/card tests from MP-031). MP-021 was exercised locally with Python 3.13. The GitHub Actions quality workflow runs manually or on PRs against `main` and executes the complete suite on Python 3.11, 3.12 and 3.13 with `SyntaxWarning` promoted to an error. MP-045 implementation run `38772141714` passed all 466 tests on every supported matrix version, plus the changed-code lint/format and dependency-policy jobs. No test connects to real sensors, physical equipment or external services.

## MP-045: expanded quality gates

The PR/manual workflow runs the complete standard-library `unittest` suite on Python 3.11, 3.12 and 3.13 with `SyntaxWarning` promoted to an error. A pinned Ruff 0.17.0 gate checks correctness rules `E4`, `E7`, `E9` and `F` plus formatter compliance for Python files changed relative to the PR base (or the `main` merge base for manual runs). This is an incremental gate; it does not claim that unchanged legacy code is clean under every Ruff rule.

`tests/test_dependency_policy.py` provides a fail-closed dependency review for this zero-runtime-dependency project: runtime and optional dependencies must remain empty, and build-system requirements must exactly match the reviewed allowlist. GitHub's Dependency Review action was evaluated first, but CI proved it is unavailable while the repository Dependency graph is disabled; the workflow therefore enforces the project-native policy instead of silently skipping dependency review.

Implementation evidence: GitHub Actions run `38772141714` — 466/466 tests passed on Python 3.11, 3.12 and 3.13; changed-code lint/format and dependency-policy jobs also passed.

## MP-046: fresh-clone reproducibility

`scripts/fresh_clone_smoke.py` is a standard-library acceptance harness for the written contributor path. A dedicated Python 3.13 CI job starts from the clean Actions checkout, creates a new temporary virtual environment, installs the checkout in editable mode, removes `PYTHONPATH`, disables user-site imports, and executes installed commands from outside the source tree. It verifies both module/console entry points, a real paused loopback server (`/api/health` plus packaged dashboard), three deterministic synthetic JSONL exports, the whole-run split, healthy-only anomaly training, and held-out `test` evaluation with provenance hashes and synthetic-only Markdown wording.

This job is intentionally separate from the 3.11/3.12/3.13 unit-test matrix: the matrix certifies supported Python behavior, while the fresh-clone job proves the documented install/run/export/evaluate workflow without tripling packaging work. It uses no IMS archive, external dataset, sensor, cloud service, or physical equipment.

Implementation evidence: GitHub Actions run `38773979137` passed all six jobs. The fresh-clone log reported `MP-046 install: ok`, `local server: ok`, `synthetic export: ok`, `held-out evaluation: ok`, and `MP-046 fresh-clone reproducibility: PASS`; the unchanged 466-test suite also passed on Python 3.11, 3.12 and 3.13, with lint/format and dependency policy green.

## MP-047: API, configuration and architecture documentation

Five standard-library documentation-contract tests in `tests/test_documentation.py` keep the contributor documentation tied to the implemented public surface. They verify README navigation, the complete localhost route table and MP-043 request limits, coverage of every installed console script, current online/offline architecture diagrams and safety boundaries, and the distinct startup-file versus HTTP configuration/error surfaces.

The consolidated entry points are `docs/API.md`, `docs/CLI.md`, `docs/TROUBLESHOOTING.md`, the refreshed `docs/ARCHITECTURE.md`, and the refreshed `docs/CONFIG_FILE.md`. Specialist guides remain the detailed source for telemetry, scenarios, history, incidents, research splits/models and local-only IMS handling. These docs make no field-validation, public-deployment, physical-control or RUL claims.

Implementation evidence: GitHub Actions run `38775790658` passed all six quality jobs. The complete suite ran **471/471** on Python 3.11, 3.12 and 3.13; changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.

## MP-048: baseline model cards and failure modes

Five standard-library contracts in `tests/test_model_cards.py` pin the canonical `docs/MODEL_CARDS.md` surface. The document has separate cards for the fixed illustrative rule baseline and the healthy-trained synthetic anomaly baseline; each records source data, intended use, inputs/outputs, validation evidence, failure modes, limitations and prohibited claims. Exact rule thresholds, sensor-quality abstentions, the five-feature anomaly contract, whole-run healthy-only training, the training-only 99th-percentile threshold and strict `score > threshold` decision are tied to implemented behavior.

The cards explicitly distinguish reproducibility/integrity evidence from physical validity and state that MotorPulse AI has **no RUL model**: MP-039 is metadata-only research/audit methodology and produces no predictions. No runtime model behavior, real-data redistribution, hardware access or industrial claims were added.

Implementation evidence: GitHub Actions run `38819182967` passed all six quality jobs. The complete suite ran **476/476** on Python 3.11, 3.12 and 3.13; changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.

## MP-049: secure local-first defaults

Six standard-library regressions in `tests/test_security.py` pin the local-only security boundary. `MotorPulseServer` now refuses non-loopback bind addresses before socket creation and validates ports before superclass initialization; HTTP requests require exactly one local `Host` header (`127.0.0.1` or `localhost`, optionally with a valid port). Startup scenario files reject symlinked files and symlinked parent components, matching the project's existing local-path hardening.

The CLI still exposes no bind-address override, unknown hardware/PLC-style control actions remain invalid synthetic control requests, and `docs/SECURITY.md` documents the unauthenticated loopback threat model, 16,384-byte HTTP JSON limit, 65,536-byte startup-config limit, symlink rules, no PLC/remote control, and no industrial safety guarantee. These are local research-tool safeguards, not authorization for network exposure.

Implementation evidence: GitHub Actions run `38820601629` passed all six quality jobs. The complete suite ran **482/482** on Python 3.11, 3.12 and 3.13; changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.

## MP-015: dated synthetic benchmark and demo media

`scripts/generate_benchmark_report.py` runs fixed `docs/examples/experiment-v1.json` through the existing MP-033 experiment pipeline, then derives `docs/BENCHMARK.md` and the self-contained `docs/demo/benchmark-summary.svg` from the resulting validation/test metrics and provenance. The report records the 2026-10-15 date, exact reproduction commands, whole-run train/validation/test groups, model-vs-rule held-out metrics, abstentions, episode delays and SHA-256 provenance, with explicit synthetic-only / not-field-performance / no-failure-probability/RUL limits.

Four tests in `tests/test_benchmark_report.py` pin README/report/media navigation, safety wording and self-contained SVG behavior. Python 3.13 additionally regenerates both committed artifacts from the fixed config into temporary paths and requires byte-for-byte equality; 3.11/3.12 validate the static contracts and skip only that Python-3.13 byte-snapshot assertion.

Implementation evidence: GitHub Actions run `38821977822` passed all six quality jobs. The suite ran **486 tests** on every supported Python; 3.13 returned OK with all four MP-015 tests executed, while 3.11/3.12 returned OK with the single Python-3.13 byte-snapshot assertion skipped by design. Changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.

## MP-050: community and issue templates

Six standard-library contracts in `tests/test_community.py` pin the public contribution surface: structured bug and feature issue forms, issue-template configuration, the pull-request checklist, current contributor guidance and safe beginner tasks. The templates require reproducibility evidence while explicitly excluding proprietary telemetry, credentials, third-party dataset records, physical-equipment controls and unsupported industrial claims.

`CONTRIBUTING.md` now links the current install, testing, security, model-card, benchmark and beginner-task guides; `docs/BEGINNER_TASKS.md` keeps starter work focused on documentation, tests and accessibility using synthetic-only fixtures rather than already-completed milestones or hardware/real-data integration.

Implementation evidence: GitHub Actions run `38822843799` passed all six quality jobs. The complete suite ran **492/492** on Python 3.11, 3.12 and 3.13; changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.

## MP-044: bounded synthetic history exports

Six standard-library/browser contracts in `tests/test_dashboard_exports.py` pin the local dashboard export boundary. The history panel exposes one CSV download for the currently loaded filtered page and three SVG downloads for the already-rendered vibration, temperature and RPM charts. Exports are created entirely in the browser from `currentRows`; there is no `/api/export` route, no backend file write and no hidden fetch of additional history pages. Buttons stay disabled until a non-empty page is loaded.

CSV output is explicitly labelled `MotorPulse AI synthetic simulation export`, includes session/asset/page metadata plus timestamp, RMS, temperature, RPM, sensor quality and rule health, and quotes cells while neutralizing leading spreadsheet-formula characters. SVG output clones the visible chart, adds a `Synthetic simulation chart` title and serializes it locally. Evaluation JSON/Markdown reports remain the existing write-once CLI/experiment artifacts rather than a browser-side recomputation.

Implementation evidence: GitHub Actions run `38829188216` passed all six permanent quality jobs. The complete suite ran **498 tests** on Python 3.11, 3.12 and 3.13 (with the existing MP-015 Python-3.13-only benchmark byte-regeneration assertion skipped by design on 3.11/3.12); changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green. The MP-044 V8 test executed CSV quote escaping and formula-prefix neutralization.

## MP-014: optional localhost SSE with polling fallback

Six regressions in `tests/test_streaming.py` pin the optional streaming boundary. `GET /api/stream` emits standard-library Server-Sent Events containing one atomic, read-only snapshot/status pair, preserves the MP-049 local Host restriction, and never advances simulation state. Disconnect/reconnect coverage proves a new connection observes the latest state after an explicit user-triggered step; no buffered replay is claimed.

The packaged dashboard uses `EventSource('/api/stream')` when supported, consumes named `state` events, and stops the legacy snapshot/status polling after a valid stream frame. If EventSource is unavailable, an event cannot be parsed, or the connection errors while the browser reconnects, the existing 1.5-second polling loop remains active as fallback. No WebSocket dependency, CORS permission, public bind, hardware integration or remote control was added.

Implementation evidence: GitHub Actions run `38830266363` passed all six permanent quality jobs on head `1fd033b6700af43c3d9e4516b0b9d6c5f931b65d`. The complete suite ran **504 tests** on Python 3.11, 3.12 and 3.13 (with the existing MP-015 Python-3.13-only benchmark byte-regeneration assertion skipped by design on 3.11/3.12); changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.

## MP-031: local-only CWRU seeded-fault adapter

Ten standard-library regressions in `tests/test_cwru.py` pin the optional CWRU boundary. The tests construct handwritten MATLAB-v5 bytes in temporary directories; they do **not** download, embed or derive from CWRU measurements. Coverage includes ordinary and zlib-compressed matrix elements, strict explicit metadata, no filename-inferred labels, bounded fail-closed MAT parsing, summary-only reports, write-once offline CLI output, packaged template/run cards and unresolved redistribution rights.

`motorpulse-cwru` accepts one user-supplied local MATLAB-v5 file plus a separate metadata JSON identifying the exact channel and seeded experimental condition. Output contains hashes and bounded descriptive summaries, never the raw sample vector or absolute local path. CWRU seeded EDM fault metadata is explicitly **not run-to-failure**: failure time, failure probability and RUL remain null. `motorpulse-card --source cwru` produces a path-free local-only provenance card and deliberately omits measurement summary values.

Official CWRU Bearing Data Center pages were reviewed for source URLs and experiment metadata, but this project did not establish an explicit dataset-specific redistribution license there. Original or derived CWRU measurement publication therefore remains `unverified_for_redistribution` / `local_only_do_not_redistribute` under project policy. Passing these tests does not prove compatibility with every real CWRU MAT file or validate industrial diagnostic performance.

Implementation evidence: GitHub Actions run `38841694707` passed all six permanent quality jobs on head `20e913f96d0e21623f8b2259a46a3d5bc4372652`. The complete suite ran **514/514** on Python 3.11, 3.12 and 3.13; changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.

For MP-035 portable JSON model artifacts, strict save/load and source validation:

```bash
python -m unittest discover -s tests -p 'test_model_artifact.py' -v
```

Tests validate model/processor consistency, deterministic round trips, strict parsing, checksum and source-card tampering, changed/missing source files, invalid versions/units/scales/thresholds, non-overwrite and MP-011/MP-033 integration without IMS data. See [MODEL_ARTIFACTS.md](MODEL_ARTIFACTS.md).

For MP-034 train-only feature transformations and temporal overlap safeguards:

```bash
python -m unittest discover -s tests -p 'test_feature_pipeline.py' -v
```

Checks cover strict feature/sampling/rolling contracts, null/nonfinite values, train group identity, duplicate windows, frozen parameters, tampering and chronological purge gaps. See [FEATURE_PIPELINE.md](FEATURE_PIPELINE.md).

For the strict, offline reproducible synthetic ML experiment runner:

```bash
python -m unittest discover -s tests -p 'test_experiment.py' -v
```

Tests cover deterministic replay, strict configurations, complete-run splits, artifact hashes, safe output ownership, failure cleanup and subprocess CLI. No real IMS data used. See [EXPERIMENTS.md](EXPERIMENTS.md).

For held-out synthetic detection metrics, PR average precision and comparable rule alerts:

```bash
python -m unittest discover -s tests -p 'test_evaluation.py' -v
```

Checks include tied scores, undefined precision/recall denominators, missed/onset episodes, quality abstentions, frozen split/model provenance, deterministic replay and write-once JSON/Markdown CLI. No third-party IMS-derived data used. See [EVALUATION.md](EVALUATION.md).

For the trained healthy-only synthetic anomaly baseline (no third-party runtime packages):

```bash
python -m unittest discover -s tests -p 'test_anomaly.py' -v
```

Tests verify grouped train-only feature fitting, held-out access guards, replay hashes, no fault-label/rule leakage into features, missing/outlier suppression, threshold boundaries, tampered files and write-once CLI. No IMS derived data or hardware measurements are used. See [ANOMALY_BASELINE.md](ANOMALY_BASELINE.md).

For machine-readable dataset-card validation and provenance checks:

```bash
python -m unittest discover -s tests -p 'test_dataset_cards.py' -v
```

Tests verify packaged template JSON, source-bound model/config/file digests, source-rights and unknown-label rules, deterministic replay, IMS local metadata-only cards, and exclusive-create CLI behavior using handwritten fixtures only. See [DATASET_CARDS.md](DATASET_CARDS.md).

For run-grouped and purged synthetic chronology split regression tests:

```bash
python -m unittest discover -s tests -p 'test_splits.py' -v
```

These tests verify seeded source-order-independent assignments, duplicate run/record rejection, source provenance, non-overlapping ranges, automatic purge minima and write-once CLI output using handwritten fixtures only. See [SPLITS.md](SPLITS.md).

For deterministic synthetic and local IMS exploratory reports:

```bash
python -m unittest discover -s tests -p 'test_eda.py' -v
```

The tests cover reproducible feature distributions, synthetic fault vs heuristic health labels, missing-vibration nulls, export-file checksum tampering, local-only IMS quality metadata, Markdown/JSON outputs and subprocess CLI. No real IMS-derived data is committed. See [EDA.md](EDA.md).

For IMS validation, train-only normalization and native-rate tone tests (all local, handwritten fixtures):

```bash
python -m unittest discover -s tests -p 'test_ims_validation.py' -v
python -m unittest discover -s tests -p 'test_ims_tone.py' -v
```

These do not validate the uninspected upstream IMS archive, sensor calibration, original licensing or physical failure-onset labels. See [IMS_VALIDATION.md](IMS_VALIDATION.md).

For local IMS-style ASCII importer validation (all fixtures handwritten, no NASA data):

```bash
python -m unittest discover -s tests -p 'test_ims.py' -v
```

These tests check channel statistics, strict timestamp/row/channel validation, fixed resource limits, local-only provenance, optional bearing map, CLI subprocess and non-overwriting reports. They **do not** prove compatibility with an original IMS archive. See [IMS_INGESTION.md](IMS_INGESTION.md).

For external-data provenance checks (offline only; no dataset download):

```bash
python -m unittest discover -s tests -p 'test_provenance.py' -v
```

These tests confirm citations, official reference URLs, rights uncertainty, unknown archive attributes and ignored raw data paths. They **do not** verify redistribution permission or the IMS archive's contents. See [DATA_PROVENANCE.md](DATA_PROVENANCE.md).

For synthetic CSV/JSONL export regression tests:

```bash
python -m unittest discover -s tests -p 'test_export.py' -v
```

The tests check content-derived IDs, stable bytes, CSV/JSONL field mapping, hashes, missing sensor records, CLI invocation, failure cleanup and non-overwrite behavior. See [DATASET.md](DATASET.md).

For scientific model and documentation guardrail tests:

```bash
python -m unittest discover -s tests -p 'test_model_reference.py' -v
```

These tests assert published sample rates, harmonic constants, threshold boundaries, scenario/example consistency and missing/outlier semantics. They do **not** validate physical accuracy; see [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md).

For focused operating variability and sensor-quality tests:

```bash
python -m unittest discover -s tests -p 'test_operations.py' -v
```

For focused local config / CLI startup tests:

```bash
python -m unittest discover -s tests -p 'test_config_file.py' -v
```

See [CONFIG_FILE.md](CONFIG_FILE.md) for accepted and rejected startup parameters.

For focused spectral/rolling tests:

```bash
python -m unittest discover -s tests -p 'test_spectral.py' -v
```

For focused packaging smoke tests (metadata, bundled dashboard, local HTTP and CLI help):

```bash
python -m unittest discover -s tests -p 'test_packaging.py' -v
```

To verify **a built wheel** from an isolated location, follow [INSTALL.md](INSTALL.md); the unit tests alone do not prove wheel contents.

For focused API regression tests:

```bash
python -m unittest discover -s tests -p 'test_contracts.py' -v
python -m unittest discover -s tests -p 'test_api_validation.py' -v
```

These integration tests bind an ephemeral `127.0.0.1` port and automatically shut down the server and simulation worker. MP-043 coverage additionally rejects duplicate JSON keys, non-standard numeric constants, excessive nesting and pathological Content-Length values; checks stable machine-readable API errors and unsupported-method handling; and verifies bad requests or persistence failures do not advance live state. They do not require the interactive dashboard to be running.

## Coverage by contract

| Area | Contract evidence | Test files |
|---|---|---|
| Telemetry v1 | Required JSON fields, optional scenario/ramp metadata, canonical units, UTC timestamp, compatibility of older fixture | `test_schema.py`, `test_contracts.py` |
| Simulation | Deterministic seed, signals, scenario onset/ramp/expiration, virtual-clock replay | `test_sim.py`, `test_clock.py`, `test_signals.py`, `test_scenarios.py`, `test_progression.py`, `test_contracts.py` |
| API read | Health, status, config, snapshots, JSON headers and no-state-change on repeated GETs | `test_controller.py`, `test_contracts.py` |
| API controls | Pause/start/step/reset, conflict when stepping while running, multiple concurrent requests | `test_controller.py`, `test_contracts.py`, `test_api_validation.py` |
| Request validation | Malformed/invalid JSON, duplicate keys, non-standard constants, nesting/body bounds, wrong Content-Type, missing/invalid/oversized Content-Length, stable error codes, unknown API paths and wrong/unsupported methods | `test_scenarios.py`, `test_controller.py`, `test_contracts.py`, `test_api_validation.py` |
| Atomic configuration | Invalid profiles leave snapshot unchanged; accepted profile replay identical after reset | `test_scenarios.py`, `test_progression.py`, `test_contracts.py`, `test_api_validation.py` |
| Browser smoke | Root page served with basic control elements, scenario and progression editor hooks | `test_contracts.py` |

### Expected response behavior (current local demo)

- `GET /api/health`, `GET /api/status`, `GET /api/snapshot`, `GET /api/config`: `200` with JSON. Only explicit control actions advance simulation ticks.
- `POST /api/control`: `200` for accepted start/pause/step/reset; `409` with `control_conflict` when stepping while running; `400` with `invalid_control_request` for invalid action/request.
- `PUT /api/config`: `200` for valid replacements and atomic paused reset; `400` with `invalid_configuration` for invalid configs.
- `PUT /api/runtime`: `200` for valid atomic runtime edits; `400` with `invalid_runtime_settings` for invalid settings.
- JSON request bodies have a **16384-byte maximum**; `415` with `unsupported_media_type` for unsupported Content-Type, `411` with `length_required` for missing/malformed Content-Length, `413` with `invalid_request_size` for empty/oversized JSON body, and `400` with `invalid_json` for malformed, duplicate-key, non-standard-number or excessively nested JSON.
- Unknown `/api/` paths and unsupported API route/method combinations return `404` with `unknown_api_endpoint`; API `HEAD` retains HEAD semantics with JSON headers and no body.
- Generic SQLite write failures return `503` with `persistence_unavailable` without exposing local filesystem paths; established history and incident lifecycle error codes remain unchanged.
- JSON responses include `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

These are regression assertions about the **current local-only demo**, not an internet-facing API SLA. Broader secure-default review remains MP-049.

## CI-minimization policy

To limit GitHub Actions usage, `.github/workflows/test.yml` is configured for `pull_request` targeting `main`, plus **manual** `workflow_dispatch`. It does **not** automatically run on every push or merge to `main`. Contributors should run local tests before a consolidated push; request a manual CI check when needed. See the [GitHub workflow syntax guide](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Test limitations

- The HTML parser checks the static page structure, **not** browser layout, keyboard navigation, or complete accessibility.
- No real devices, external databases, ML model training, deployment, authentication, pressure/load benchmarks, or high-volume multi-process races are covered.
- The runtime v1 validator enforces important cross-field constraints but is not a complete JSON Schema implementation.
- The simulator's thresholds and waveform assumptions are synthetic. Passing tests is not evidence of predictive fault diagnosis or safety certification.

## MP-039: RUL research gate, not an RUL benchmark

```bash
python -m unittest discover -s tests -p 'test_rul_research.py' -v
```

The handwritten metadata fixture is **fictional and intentionally blocked**. Regression tests validate explicit observed failure versus censored follow-up, UTC chronology, physically disjoint asset splits, self-declared rights/label review safeguards, deterministic report fingerprints and no-overwrite CLI exports. The tool does not calculate an RUL or verify raw NASA IMS data. See [RUL_RESEARCH.md](RUL_RESEARCH.md).

## MP-012: opt-in SQLite persistence, restarts and write atomicity

```bash
python -m unittest discover -s tests -p 'test_storage.py' -v
```

The 19 offline SQLite/history tests cover full JSON snapshots, per-event alerts and missing/outlier quality, schema upgrades, restart/reset/configuration history, parameterized pagination, simulated transaction write errors, automatic-worker fail-closed behavior, default no-database mode, symlink rejection, concurrency and localhost HTTP integration. No real machines or third-party SQLite package are used. See [SQLITE_HISTORY.md](SQLITE_HISTORY.md).

## MP-040: read-only localhost history REST contracts

```bash
python -m unittest discover -s tests -p 'test_history_api.py' -v
```

21 new offline tests exercise four history endpoints, response schemas and headers, source/session/motor filtering, microsecond UTC boundaries, newest-first id pagination during concurrent insertions, exact page termination, invalid/malformed/duplicate query parameters, missing database 409, SQLite read failure 503 and restart-safe history. The existing simulator GET/snapshot behavior is unchanged. See [HISTORY_API.md](HISTORY_API.md).

## MP-042: synthetic rule incident lifecycle and review

```bash
python -m unittest discover -s tests -p 'test_incidents.py' -v
```

24 tests check deduplicated incidents, severity/reason changes, normal recovery versus missing/outlier interruptions, session isolation, schema v2-to-v3 backfill, persistent once-only local review with separate wall UTC, transactional SQLite failure rollback, validated/paginated localhost REST and dashboard packaging/accessibility. Existing migration tests now expect v3. See [ALERT_LIFECYCLE.md](ALERT_LIFECYCLE.md).

## MP-043: API request validation and safe failure semantics

```bash
python -m unittest discover -s tests -p 'test_api_validation.py' -v
```

Six loopback tests cover strict JSON parsing, bounded body framing, stable machine-readable error codes, unsupported API methods and rollback/non-mutation under invalid input or SQLite write failure. They preserve the localhost-only architecture and do not add authentication, public binding, remote control or physical-device access.

## MP-013: historical charts, filters and accessible table

```bash
python -m unittest discover -s tests -p 'test_history_dashboard.py' -v
```

16 offline unittest cases cover packaged SVG/chart-script assets, inclusive UTC browser controls, prior-session/motor source filtering and pagination, simulated missing/outlier vibration gaps (never interpolated), table quality labels, immutable history GET, disabled-database fallback, responsive labels and live reset integration. When Node.js is already present in the developer/CI environment, optional V8 tests execute the actual client chart code against a test DOM, verifying 1-microsecond time resolution and safe missing-value display. No Node or chart package is needed for the running application. See [HISTORICAL_DASHBOARD.md](HISTORICAL_DASHBOARD.md).

## MP-041: dashboard seed and virtual/real clock controls

```bash
python -m unittest discover -s tests -p 'test_runtime_controls.py' -v
```

13 dependency-free offline checks exercise strict PUT /api/runtime validation, deterministic paused tick-1 replay, real versus simulated clock spacing, SQLite session preservation and atomic rollback, background-worker pause, original motor scenario retention, localhost API errors and the dashboard's accessible labelled inputs and responsive layout. No browser automation, hardware or external network is required. See [RUNTIME_CONTROLS.md](RUNTIME_CONTROLS.md).
