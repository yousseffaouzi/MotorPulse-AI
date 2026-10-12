# MotorPulse AI — Local testing and contract coverage (MP-021)

MotorPulse AI is a **software-only industrial motor simulation**, not a trained predictive-maintenance service or production control system. These regression tests verify software behavior, not accuracy on physical motors.

## Run locally

From the repository root, using Python 3.11 or later and **no third-party packages**:

```bash
python -m unittest discover -s tests -v
```

The suite contains **294 standard-library unittest test cases** (64 through MP-021, 4 packaging smoke tests from MP-022, 13 spectral/rolling checks from MP-023, 9 JSON/CLI startup tests from MP-024, 11 sensor/operating tests from MP-025, 7 model-reference regression tests from MP-026, 12 export/manifest regression tests from MP-008, 10 offline source-card/provenance checks from MP-027, 15 offline local IMS-style parser tests from MP-009, 18 IMS report/normalization tests and 6 native-tone tests from MP-028, 18 exploratory report/CLI regression tests from MP-029, 16 whole-run/chronological split tests from MP-030, 16 dataset-card/provenance/CLI tests from MP-032, 19 trained-anomaly/sensor-gating/split-leakage tests from MP-010, 21 held-out detection/report tests from MP-011, 16 reproducible experiment/CLI tests from MP-033, and 19 feature/temporal-leakage tests from MP-034). MP-021 was exercised locally with Python 3.13; the GitHub Actions workflow can be run manually or on PRs against `main` with Python 3.12. Other versions are not yet verified in this milestone. No test connects to real sensors or external services.

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
```

These integration tests bind an ephemeral `127.0.0.1` port and automatically shut down the server and simulation worker. They do not require the interactive dashboard to be running.

## Coverage by contract

| Area | Contract evidence | Test files |
|---|---|---|
| Telemetry v1 | Required JSON fields, optional scenario/ramp metadata, canonical units, UTC timestamp, compatibility of older fixture | `test_schema.py`, `test_contracts.py` |
| Simulation | Deterministic seed, signals, scenario onset/ramp/expiration, virtual-clock replay | `test_sim.py`, `test_clock.py`, `test_signals.py`, `test_scenarios.py`, `test_progression.py`, `test_contracts.py` |
| API read | Health, status, config, snapshots, JSON headers and no-state-change on repeated GETs | `test_controller.py`, `test_contracts.py` |
| API controls | Pause/start/step/reset, conflict when stepping while running, multiple concurrent requests | `test_controller.py`, `test_contracts.py` |
| Request validation | Malformed/invalid JSON, wrong Content-Type, missing/invalid/oversized Content-Length, unknown API paths and wrong route/method combinations | `test_scenarios.py`, `test_controller.py`, `test_contracts.py` |
| Atomic configuration | Invalid profiles leave snapshot unchanged; accepted profile replay identical after reset | `test_scenarios.py`, `test_progression.py`, `test_contracts.py` |
| Browser smoke | Root page served with basic control elements, scenario and progression editor hooks | `test_contracts.py` |

### Expected response behavior (current local demo)

- `GET /api/health`, `GET /api/status`, `GET /api/snapshot`, `GET /api/config`: `200` with JSON. Only explicit control actions advance simulation ticks.
- `POST /api/control`: `200` for accepted start/pause/step/reset; `409` when stepping while running; `400` for invalid action/request.
- `PUT /api/config`: `200` for valid replacements and atomic paused reset; `400` for invalid configs.
- JSON request bodies have a **16384-byte maximum**; `415` for unsupported Content-Type, `411` for missing/malformed Content-Length, `413` for empty/oversized JSON body.
- Unknown `/api/` paths, and POST/PUT on the wrong endpoint, currently return `404` JSON errors.
- JSON responses include `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

These are regression assertions about the **current demo**, not an internet-facing API SLA. Local HTTP implementations may evolve as explicit error-handling and security milestones proceed (MP-043 / MP-049).

## CI-minimization policy

To limit GitHub Actions usage, `.github/workflows/test.yml` is configured for `pull_request` targeting `main`, plus **manual** `workflow_dispatch`. It does **not** automatically run on every push or merge to `main`. Contributors should run local tests before a consolidated push; request a manual CI check when needed. See the [GitHub workflow syntax guide](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Test limitations

- The HTML parser checks the static page structure, **not** browser layout, keyboard navigation, or complete accessibility.
- No real devices, external databases, ML model training, deployment, authentication, pressure/load benchmarks, or high-volume multi-process races are covered.
- The runtime v1 validator enforces important cross-field constraints but is not a complete JSON Schema implementation.
- The simulator's thresholds and waveform assumptions are synthetic. Passing tests is not evidence of predictive fault diagnosis or safety certification.
