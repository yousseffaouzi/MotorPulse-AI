# MotorPulse AI — Local testing and contract coverage (MP-021)

MotorPulse AI is a **software-only industrial motor simulation**, not a trained predictive-maintenance service or production control system. These regression tests verify software behavior, not accuracy on physical motors.

## Run locally

From the repository root, using Python 3.11 or later and **no third-party packages**:

```bash
python -m unittest discover -s tests -v
```

The suite contains **130 standard-library unittest test cases** (64 through MP-021, 4 packaging smoke tests from MP-022, 13 spectral/rolling checks from MP-023, 9 JSON/CLI startup tests from MP-024, 11 sensor/operating tests from MP-025, 7 model-reference regression tests from MP-026, 12 export/manifest regression tests from MP-008, and 10 offline source-card/provenance checks from MP-027). MP-021 was exercised locally with Python 3.13; the GitHub Actions workflow can be run manually or on PRs against `main` with Python 3.12. Other versions are not yet verified in this milestone. No test connects to real sensors or external services.

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
