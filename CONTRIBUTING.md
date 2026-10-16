# Contributing to MotorPulse AI

MotorPulse AI is a local-first, software-only **synthetic motor monitoring research lab**. Contributions to documentation, accessibility, deterministic simulation, tests, local APIs, reproducibility tooling and carefully bounded research workflows are welcome. The project is not an industrial safety system, field-validated diagnostic product, failure-probability service or RUL predictor.

## Before opening a change

1. Read the [installation guide](docs/INSTALL.md) and [testing guide](docs/TESTING.md).
2. Check the current roadmap in `TODO.md` and use the structured GitHub issue forms for bugs or feature proposals.
3. For a small first change, choose a current [beginner task](docs/BEGINNER_TASKS.md) rather than an already-completed milestone.
4. Review [local-first security](docs/SECURITY.md), [model cards](docs/MODEL_CARDS.md), and the [dated synthetic benchmark](docs/BENCHMARK.md) before changing public claims, deployment assumptions or model/evaluation behavior.

Do not submit real or proprietary machine telemetry, credentials, private datasets, copyrighted industrial control configurations, secrets, or customer data. NASA IMS archives and real-data-derived reports/features must remain outside the repository until redistribution/reuse rights are explicitly reviewed and documented.

## Local setup and tests

Use Python 3.11 or later. Runtime dependencies remain empty.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

The PR quality workflow exercises Python 3.11, 3.12 and 3.13, changed-code Ruff lint/format, the dependency policy, and the fresh-clone install/run/export/evaluate path. Add focused regression tests for changed behavior and keep generated outputs deterministic when the relevant contract requires it.

## Data and scientific boundaries

Synthetic truth is useful for software tests; it is not physical validation. Keep these invariants intact:

- external data stays local unless source rights and redistribution terms are independently reviewed;
- ML preprocessing, model fitting and original thresholds use training data only;
- grouped **whole-run** boundaries prevent the project's supported anomaly baseline from fitting on held-out runs;
- validation/test remain **held-out** for evaluation or explicitly validation-only threshold-selection work;
- sensor missing/outlier states remain abstentions where the documented evaluation contract requires them;
- model artifacts remain non-executable, source-linked JSON with strict verification;
- benchmark, robustness and comparison metrics remain labelled synthetic-only and not field performance.

Relevant specialist references include [dataset cards](docs/DATASET_CARDS.md), [data provenance](docs/DATA_PROVENANCE.md), [splits](docs/SPLITS.md), [healthy-only anomaly training](docs/ANOMALY_BASELINE.md), [feature pipelines](docs/FEATURE_PIPELINE.md), [held-out evaluation](docs/EVALUATION.md), [experiments](docs/EXPERIMENTS.md), and [portable artifacts](docs/MODEL_ARTIFACTS.md).

## Local-first and safety boundaries

Do not broaden the server beyond its `127.0.0.1` local-only boundary or add a public bind flag as an incidental contribution. Do not add PLC, SCADA, GPIO, serial/fieldbus actuation, remote machinery control, production alarm guarantees or automatic maintenance actions. Real sensors, edge/PLC integration and remote deployment remain a separate on-hold phase requiring explicit security and evaluation approval.

File/path changes should preserve strict size limits, symlink protections, non-overwrite behavior and path-redacted API failures where those contracts already exist. Never add credentials or secrets to fixtures, examples, logs or issue reports.

## Pull requests

Create a focused branch and keep commits reviewable. In the PR:

- explain the problem and the smallest implemented change;
- list exact acceptance evidence and tests;
- update documentation when commands, schemas, limits, assumptions or public behavior change;
- state data/provenance and security/local-first impact;
- include a synthetic-only screenshot or generated example when a UI/report change benefits from it;
- avoid real-world performance, failure-probability, RUL or industrial-safety claims unless independently supported by a future approved validation program.

The repository PR template contains the required review checklist. `main` should stay releasable and reproducible; do not bypass failing quality gates just to land a change.
