# MotorPulse AI CLI tutorial

MotorPulse AI is a **local-first synthetic research lab**. The installed commands below operate on synthetic data or user-provided local files; they do not connect to sensors, PLCs, cloud services, or physical motors. Outputs are research artifacts, not validated industrial diagnoses or remaining-useful-life predictions.

Install from a fresh clone using Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
```

The end-to-end synthetic path below is the same class of install/run/export/evaluate workflow exercised by the MP-046 fresh-clone CI job. Detailed installation/offline notes are in [INSTALL.md](INSTALL.md).

## 1. Run the localhost simulator

`motorpulse-ai` is equivalent to `python -m motorpulse`:

```bash
motorpulse-ai --paused
# open http://127.0.0.1:8765
```

Useful startup options:

```bash
motorpulse-ai \
  --config docs/examples/scenarios-progressive.json \
  --seed 72 \
  --start-time-utc 2026-05-20T12:00:00Z \
  --step-seconds 2.5 \
  --interval-seconds 0.5 \
  --paused \
  --port 8766
```

Add `--database ./motorpulse-local.sqlite3` only when you want opt-in local SQLite history/incidents. The server always binds to `127.0.0.1`; `--port` does not make it a supported network service. See [API.md](API.md), [CONFIG_FILE.md](CONFIG_FILE.md), and [RUNTIME_CONTROLS.md](RUNTIME_CONTROLS.md).

## 2. Export deterministic synthetic feature events

Create the parent directory, then export one new run directory per seed. Existing destinations are not overwritten.

```bash
mkdir -p datasets

motorpulse-export --out-dir datasets/run-11 --ticks 30 --seed 11 --format jsonl
motorpulse-export --out-dir datasets/run-22 --ticks 30 --seed 22 --format jsonl
motorpulse-export --out-dir datasets/run-33 --ticks 30 --seed 33 --format jsonl
```

Each run contains a checksummed manifest and labelled synthetic events. This is generated simulation data, not measured machinery data. Full fields and reproducibility rules: [DATASET.md](DATASET.md).

## 3. Build a leakage-resistant whole-run split

```bash
motorpulse-split \
  --source synthetic \
  --input datasets/run-11/manifest.json datasets/run-22/manifest.json datasets/run-33/manifest.json \
  --seed 42 \
  --out datasets/split.json
```

The split planner keeps complete source runs together. It does not fit a model. See [SPLITS.md](SPLITS.md).

## 4. Fit the healthy-only anomaly baseline

```bash
motorpulse-anomaly \
  --split datasets/split.json \
  --input datasets/run-11/manifest.json datasets/run-22/manifest.json datasets/run-33/manifest.json \
  --out datasets/model.json
```

Training-only feature scaling and threshold fitting are bound to verified training groups. Validation/test measurements are not used to fit this model. See [ANOMALY_BASELINE.md](ANOMALY_BASELINE.md) and [FEATURE_PIPELINE.md](FEATURE_PIPELINE.md).

## 5. Evaluate the held-out test partition

```bash
motorpulse-evaluate \
  --split datasets/split.json \
  --model datasets/model.json \
  --input datasets/run-11/manifest.json datasets/run-22/manifest.json datasets/run-33/manifest.json \
  --partition test \
  --out datasets/test-report.json \
  --markdown datasets/test-summary.md
```

The report compares the frozen anomaly baseline and transparent rules on the eligible **held-out** synthetic cohort. Metrics are simulation research metrics; they do not establish physical predictive-maintenance accuracy. See [EVALUATION.md](EVALUATION.md).

## 6. One-command reproducible synthetic experiment

For a larger orchestrated workflow, `motorpulse-experiment` creates exports, source cards, a whole-run split, frozen model/evaluations, and a checksummed artifact index from a strict local JSON experiment configuration. See [EXPERIMENTS.md](EXPERIMENTS.md) for the canonical configuration example and artifact layout.

```bash
motorpulse-experiment --help
```

## Installed command map

The package installs the following console scripts. Use each command's `--help` plus the linked specialist guide for its exact options.

| Command | Purpose | Primary guide |
| --- | --- | --- |
| `motorpulse-ai` | Localhost synthetic simulator/dashboard/API | [INSTALL.md](INSTALL.md), [API.md](API.md) |
| `motorpulse-export` | Reproducible synthetic CSV/JSONL feature-event export | [DATASET.md](DATASET.md) |
| `motorpulse-ims` | Inspect **user-provided local** IMS-style ASCII records | [IMS_INGESTION.md](IMS_INGESTION.md) |
| `motorpulse-ims-validate` | Validate/report local IMS-style records with declared metadata | [IMS_VALIDATION.md](IMS_VALIDATION.md) |
| `motorpulse-eda` | Generate deterministic synthetic or local-IMS exploratory reports | [EDA.md](EDA.md) |
| `motorpulse-split` | Create whole-run train/validation/test split plans | [SPLITS.md](SPLITS.md) |
| `motorpulse-card` | Read/create provenance-bound dataset cards | [DATASET_CARDS.md](DATASET_CARDS.md) |
| `motorpulse-anomaly` | Fit/preview the healthy-only synthetic anomaly baseline | [ANOMALY_BASELINE.md](ANOMALY_BASELINE.md) |
| `motorpulse-evaluate` | Evaluate frozen models on validation/test partitions | [EVALUATION.md](EVALUATION.md) |
| `motorpulse-experiment` | Orchestrate strict reproducible synthetic experiments | [EXPERIMENTS.md](EXPERIMENTS.md) |
| `motorpulse-model` | Create/verify strict portable JSON model artifacts | [MODEL_ARTIFACTS.md](MODEL_ARTIFACTS.md) |
| `motorpulse-robustness` | Slice frozen held-out synthetic evaluations by regime | [ROBUSTNESS.md](ROBUSTNESS.md) |
| `motorpulse-compare` | Explain same-window rule-vs-model outcomes/examples | [COMPARISON.md](COMPARISON.md) |
| `motorpulse-calibrate` | Select validation-only anomaly thresholds under false-alarm budgets | [CALIBRATION.md](CALIBRATION.md) |
| `motorpulse-rul-audit` | Audit whether a dataset even supports a separate RUL research question | [RUL_RESEARCH.md](RUL_RESEARCH.md) |

## IMS is local-only and rights-sensitive

The IMS commands never download an archive. You must supply already-obtained local files and the required metadata. MotorPulse AI does **not** redistribute NASA IMS raw or derived waveforms; dataset-specific redistribution/derivative rights remain a separate review concern. Do not infer synthetic 1024 Hz units, fault labels, or RUL labels for IMS records. See [DATA_PROVENANCE.md](DATA_PROVENANCE.md).

## Output ownership and reproducibility

Most offline commands use fail-closed output semantics: existing files/directories are not silently overwritten, provenance hashes are checked before downstream use, and split/model identities must match their source manifests. If a command rejects an existing output, choose a new path or intentionally remove your previous local artifact after deciding it is safe to do so.

For a complete clean-checkout acceptance run, execute:

```bash
python scripts/fresh_clone_smoke.py
```

That script installs into an isolated temporary virtual environment, runs commands from outside the checkout, starts/stops the loopback server, exports three synthetic runs, creates the whole-run split, trains the healthy-only baseline, and evaluates the held-out `test` partition. It uses no IMS archive or hardware.

For common install, port, JSON, SQLite, and output-path failures, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
