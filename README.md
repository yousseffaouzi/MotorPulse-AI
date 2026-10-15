# MotorPulse AI

**Software-first predictive-maintenance lab for industrial motors and rotating equipment.**

> **Status:** pre-alpha simulated prototype. The current alerts are explainable rule-based baselines, **not** a trained predictive-maintenance AI model. All demo measurements are synthetic; no hardware is required.

## What you can run today
- Reproducible simulated vibration, temperature and RPM signals for three motors.
- RPM-linked synthetic vibration at 1× and 2× shaft speed, plus illustrative bearing impacts.
- Five configurable synthetic scenarios: healthy, imbalance, bearing wear, misalignment, and overload; per-asset severity, onset, optional duration, and local JSON startup files.
- Feature extraction: vibration RMS, peak-to-peak amplitude, crest factor, Hann-windowed spectral features and 5-tick rolling summaries.
- Synthetic speed/load variability, vibration noise/drift, missing sensor intervals and outliers with explicit sensor-quality states.
- Deterministic, bounded CSV/JSONL **synthetic** dataset export with sensor labels and a checksummed provenance manifest.
- Reviewed official IMS bearing-dataset sources and citations, with explicit third-party reuse restrictions and no bundled real data.
- Optional bounded IMS-style **local-only** ASCII record importer using user-declared sampling metadata and no assumed defect labels.
- Local IMS report integrity/chronology checks, native-rate Hann single-bin amplitude and train-only feature normalization across disjoint runs.
- Reproducible synthetic and local-only IMS **exploratory quality reports** (numeric distributions, missingness, trends and provenance in JSON or Markdown).
- Deterministic **train/validation/test split plans** that keep complete source runs together, reject duplicate groups, and offer explicitly exploratory synthetic chronological holdouts with purge gaps.
- Versioned **dataset cards** for synthetic events and IMS source metadata, with local provenance-bound run cards and explicit licensing limitations.
- First **trained synthetic-only anomaly baseline**: healthy-window standardized distance, training-only 99th-percentile threshold, strict whole-run split provenance and sensor-quality-aware scoring.
- Held-out synthetic performance reports: shared eligible cohorts, precision/recall/F1, PR average precision, false alarms and scripted fault-episode detection delays.
- One-command **reproducible synthetic ML experiments**: source runs, dataset cards, split, trained model, held-out metrics, Markdown report and SHA-256 artifact index.
- Versioned **train-only feature preprocessing** with fixed feature/measurement contracts, source-group hashes and chronological overlap/purge safeguards.
- **Portable, verified model artifacts**: strict non-executable JSON, source/split/dataset-card identity checks, frozen preprocessing and deterministic SHA-256.
- Transparent rule-based health classification with fault examples.
- Local REST endpoints and a dashboard with Start/Pause/Step/Reset controls.
- Unit tests via the Python standard library. **No Docker, cloud account, or hardware required.**

## Quick start
Requires Python 3.11+. **From a fresh clone**, you can run directly without installing:

```bash
python -m motorpulse
# open http://127.0.0.1:8765
```

Or install locally for development (macOS/Linux; on Windows activate the corresponding PowerShell virtual environment):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
motorpulse-ai
```

The `motorpulse-ai` command and `python -m motorpulse` are equivalent; the dashboard is included with the installed package. To run at a different virtual clock speed:

```bash
python -m motorpulse --seed 42 --start-time-utc 2026-01-01T00:00:00Z --step-seconds 2 --interval-seconds 0.5
```

See [docs/INSTALL.md](docs/INSTALL.md) for wheel builds, offline options, cross-directory verification, and troubleshooting.

Contributor references: [localhost API](docs/API.md), [CLI tutorial](docs/CLI.md), [troubleshooting](docs/TROUBLESHOOTING.md), [architecture](docs/ARCHITECTURE.md), [configuration](docs/CONFIG_FILE.md), [baseline model cards](docs/MODEL_CARDS.md), and [local-first security](docs/SECURITY.md).

To **launch with a saved motor configuration**, e.g. a reproducible progressive-fault demo:

```bash
python -m motorpulse --config docs/examples/scenarios-progressive.json --paused
```

You may also add `--seed 72 --start-time-utc 2026-05-20T12:00:00Z --step-seconds 2.5 --port 8766`. The `--paused` flag leaves the simulator at tick 1 for deterministic inspection. Paths are relative to the current directory. See [docs/CONFIG_FILE.md](docs/CONFIG_FILE.md) for strict validation and examples.

In another terminal, you can query a JSON snapshot:

```bash
curl http://127.0.0.1:8765/api/snapshot
curl http://127.0.0.1:8765/api/status

# Pause, then advance exactly one tick:
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"pause"}'
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"step"}'
```

Run the complete standard-library test suite locally:

```bash
python -m unittest discover -s tests -v
```

To **export a labelled synthetic dataset** (make the parent directory first):

```bash
mkdir -p datasets
python -m motorpulse.export --out-dir datasets/demo-001 --ticks 12 --format both \
  --config docs/examples/operations-v1.json --seed 42
```

This creates `events.csv`, `events.jsonl`, and `manifest.json` with SHA-256 checksums, simulated timestamps and explicit sensor-quality labels. No destination files are overwritten. Installed packages also offer `motorpulse-export`. Read [docs/DATASET.md](docs/DATASET.md) for the full field dictionary, null conventions, reproducibility rules, size limits, and safety caveats.

For API contract tests only:

```bash
python -m unittest discover -s tests -p 'test_contracts.py' -v
```

See [docs/TESTING.md](docs/TESTING.md) for endpoint behavior, request validation, concurrency, replay coverage and known limitations.

## Software architecture

```text
Synthetic multi-motor simulator -> Signal features -> Transparent baseline rules
                                      |                         |
                                      +------- JSON API -------+
                                               |
                                       Browser dashboard
```

- `motorpulse/signals.py` — synthetic RPM-related acceleration waveform fixtures.
- `motorpulse/spectral.py` — dependency-free FFT, one-sided band power and harmonic peak estimates.
- `docs/SPECTRAL.md` — spectral frequency/units conventions, rollup definitions and limits.
- `docs/OPERATIONS.md` — operational variability, missing/outlier sensor behavior and caveats.
- `docs/MODEL_ASSUMPTIONS.md` — authoritative equations, units, thresholds, provenance and scientific limitations.
- `motorpulse/export.py` / `docs/DATASET.md` — dependency-free CSV/JSONL synthetic export, per-run provenance and field dictionary.
- `docs/DATA_PROVENANCE.md` / `docs/sources/ims-bearings.source.json` — NASA IMS source citation, verification status, license uncertainty, safe user-side acquisition instructions and future validation requirements.
- `motorpulse/ims.py` / `docs/IMS_INGESTION.md` — bounded, local, user-supplied IMS-style ASCII ingestion and provenance-only reports; no copied real archive data.
- `motorpulse/ims_validation.py`, `motorpulse/ims_tone.py` / `docs/IMS_VALIDATION.md` — local data-quality checks, optional native-rate tone analysis and leakage-safe train-only scaling.
- `motorpulse/eda.py` / `docs/EDA.md` — deterministic exploratory distributions, missingness, trend samples, hashes, and explicit synthetic/IMS source separation.
- `motorpulse/splits.py` / `docs/SPLITS.md` — train/validation/test split plans with whole-run boundaries, deterministic seeded assignment and synthetic-only chronological purge gaps.
- `motorpulse/cards/*.json`, `motorpulse/dataset_cards.py` / `docs/DATASET_CARDS.md` — versioned dataset cards, source-bound metadata and rights/label safeguards.
- `motorpulse/anomaly.py` / `docs/ANOMALY_BASELINE.md` — trained healthy-only synthetic feature baseline with data-leakage checks, train-calibrated threshold and separate rule-based health preview.
- `motorpulse/evaluation.py` / `docs/EVALUATION.md` — whole-run held-out synthetic detection metrics, fair rule comparison, PR average precision, abstentions and virtual-time fault-episode delays.
- `motorpulse/experiment.py` / `docs/EXPERIMENTS.md` — one strict JSON-configured offline synthetic experiment command with grouped splits, trained model, validation/test reports and deterministic artifact provenance.
- `motorpulse/feature_pipeline.py` / `docs/FEATURE_PIPELINE.md` — train-only, SHA-256-bound feature scaling, sampling/rolling contracts and independent synthetic chronological overlap checks.
- `motorpulse/model_artifact.py` / `docs/MODEL_ARTIFACTS.md` — strict portable synthetic model JSON, source-linked save/load/verify CLI, safe compatibility checks and MP-033 artifact integration.
- `motorpulse/robustness.py` / `docs/ROBUSTNESS.md` — source-verified held-out synthetic regime slices with frozen model/rule comparisons and abstention-aware reports.
- `motorpulse/comparison.py` / `docs/COMPARISON.md` — explainable same-window MP-003 rules versus frozen MP-010 model with concrete synthetic false-positive and sensor-abstention examples.
- `motorpulse/calibration.py` / `docs/CALIBRATION.md` — validation-only, tie-aware empirical false-alarm budget selection and separate untouched synthetic test audit.
- `motorpulse/sim.py` — reproducible synthetic source and baseline classification.
- `docs/SIGNALS.md` — sample-rate, Nyquist, harmonics, and modeling limitations.
- `docs/SCENARIOS.md` — configuration API, fault types, severity and timing semantics.
- `motorpulse/config_file.py` / `docs/CONFIG_FILE.md` — bounded UTF-8 JSON startup loading and CLI guidance.
- `motorpulse/controller.py` — thread-safe, timed simulator worker.
- `motorpulse/__main__.py` — localhost demo server.
- `docs/SIMULATION_CONTROL.md` — simulation controls and virtual clock configuration.
- `motorpulse/web/index.html` — dashboard embedded in source and installed wheels.
- `docs/ARCHITECTURE.md` — design choices and future extensibility.
- `TODO.md` — issue-ready tracker with explicit status.
- `docs/TESTING.md` — API, replay, schema and concurrent-request regression test guide.
- `pyproject.toml` — installation metadata, console script and package asset inclusion.

## Telemetry contract (v1)

The JSON snapshot now includes `schema_version`, stable per-simulation-event IDs, UTC measurement timestamps, explicit sensor units, sample rate and sample count. See [docs/TELEMETRY.md](docs/TELEMETRY.md), [the JSON Schema](docs/snapshot.schema.json), and [a validated example](docs/examples/snapshot-v1.json). Existing dashboard measurement fields remain compatible. Since MP-018, timestamps come from a deterministic **UTC virtual clock**, not the host wall clock. Tick 1 occurs at the configured start time (default: `2026-01-01T00:00:00+00:00`), and each tick advances by `--step-seconds` (default: 1.5). Reset reproduces the same complete JSON snapshot sequence. `--interval-seconds` controls execution speed only. The telemetry schema version remains 1.0.0.

## MP-019 signal sampling

Acceleration is generated at **1024 samples/second** over a **1-second window** (1024 samples; 1 Hz bin spacing). The shaft's 1× frequency is **RPM/60 Hz**, with a small 2× harmonic. The synthetic imbalance scenario increases 1× amplitude; bearing wear adds pulses at an **illustrative 4.8× ratio**, not a geometry-derived bearing defect frequency. The misalignment scenario is also selectable in the dashboard. All fault amplitudes remain educational fixtures. The timestamp is the virtual start of the acquisition window. Read [docs/SIGNALS.md](docs/SIGNALS.md) before interpreting these patterns.

## Configurable fault scenarios (MP-007)

Use the dashboard to choose a fault for each motor and adjust its severity (0–1), onset tick, and optional duration. Clicking **Apply scenarios** atomically replaces the in-memory configuration, pauses, and resets the simulation to tick 1. These values are **illustrative**, not industrial severity calibration. The original seed and virtual clock settings are preserved.

For scripts, read `GET /api/config` and replace all assets with `PUT /api/config` using `Content-Type: application/json` (1–12 motors, validation before mutation). You can load a reproducible example:

```bash
curl -X PUT http://127.0.0.1:8765/api/config -H 'Content-Type: application/json' --data-binary @docs/examples/scenarios-v1.json
```

See [docs/SCENARIOS.md](docs/SCENARIOS.md) for behavior, input constraints and limitations. By default a scenario holds constant severity while active, preserving older configurations. MP-020 adds optional linear or exponential severity ramps.

## Progressive degradation simulation (MP-020)

The dashboard now supports `constant`, `linear`, and `exponential` **synthetic** fault progression. For a ramp, set target `severity`, `start_severity`, and `ramp_ticks` (at least 2, including both endpoints). Onset and optional duration work as before. The motor cards show current severity, phase, and a **configured trajectory preview** (not historical sensor readings). Reset deterministically replays the same ramp.

```bash
curl -X PUT http://127.0.0.1:8765/api/config -H 'Content-Type: application/json' --data-binary @docs/examples/scenarios-progressive.json
```

See [docs/PROGRESSION.md](docs/PROGRESSION.md) for exact ramp equations, validation, and limitations. These curves are illustrative only; no field calibration or remaining-useful-life model is claimed.

## Python packaging (MP-022)

MotorPulse AI is packaged as **motorpulse-ai 0.1.0.dev0** (development-only metadata; **not published to PyPI**). All runtime modules are standard-library-only; installing or building the wheel needs Python packaging tools. The single source of truth for the dashboard is now `motorpulse/web/index.html`, so it works after installing from a wheel even when launched from another working directory. See [docs/INSTALL.md](docs/INSTALL.md) for instructions and smoke checks.

## Spectral and rolling indicators (MP-023)

Per motor, the dashboard now shows Hann-windowed **1×/2× shaft peak amplitudes (g peak)**, **80–400 Hz acceleration band RMS (g RMS)**, and a **five-simulation-tick average of vibration RMS**. The frequency bin spacing is 1 Hz at the default 1024 Hz / 1024 sample window. An efficient dependency-free radix-2 FFT keeps the zero-runtime-dependency promise. The simulation history is per motor and only advances when a new synthetic tick is produced, never from polling; reset replays the same values. These indicators are *not* validated diagnostic thresholds or trained predictions. Full definitions: [docs/SPECTRAL.md](docs/SPECTRAL.md).

## Local scenario configuration (MP-024)

The CLI accepts `--config <local-file.json>` with the same validated `assets` schema as the existing configuration API. It rejects duplicate JSON keys, oversized or malformed files, invalid fault settings, and non-finite numbers **before opening the server**. `--paused` and `--port` allow isolated local testing. Runtime dependencies remain zero, and all options bind only to `127.0.0.1`. Documentation: [docs/CONFIG_FILE.md](docs/CONFIG_FILE.md).

## Operational variability and sensor events (MP-025)

Motors now support configured speed/load fluctuations, sensor noise, drift, missing vibration windows and outlier injections. The simulator keeps machine fault truth separate from the sensor status: missing vibration yields JSON `null` and `health="unavailable"`, while an injected outlier is `health="suspect"`. Neither automatically proves a motor defect. The dashboard shows these statuses and avoids displaying missing features as zero.

```bash
python -m motorpulse --config docs/examples/operations-v1.json --paused
```

Step through the simulation to inspect onset and recovery. Parameter limits, provenance, and simplified physical assumptions: [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Simulation model and scientific limitations (MP-026)

**Read [docs/MODEL_ASSUMPTIONS.md](docs/MODEL_ASSUMPTIONS.md) before using or exporting synthetic readings.** It consolidates the formulas and units for shaft harmonics, illustrative bearing pulses, thermal offsets, configurable operating conditions, fault-severity curves, FFT features, and sensor-quality events. The current 'health' classes are **uncalibrated demo rules**, not a trained failure predictor; synthetic fault labels are not real diagnostic evidence. The documentation distinguishes g peak, g RMS, temperature, RPM, and simulated UTC time.

## Synthetic dataset export (MP-008)

Use `python -m motorpulse.export --out-dir NEW_DIRECTORY --ticks 100 --format both [--config FILE]` to export one event per motor per virtual tick. Each export has a stable content-derived `export_id`; the data records and checksums replay for the same inputs and model-source files. The manifest separately records the **real** creation time, which can change between exports. Missing vibration remains **JSON null / CSV blank**, not zero. This is not real sensor data, a trained prediction or a validated maintenance decision. See [docs/DATASET.md](docs/DATASET.md).

## IMS bearing dataset provenance (MP-027)

The next real-data benchmark may use the **IMS Bearings** experimental archive, originally supplied by the University of Cincinnati and distributed through NASA's PCoE repository. The public NASA catalog's license badge is `other-license-specified`; the upstream archive's exact third-party redistribution and derived-data reuse permissions have **not been verified**. Therefore **no original bearing data is included or republished**, even though NASA provides download links. The source card records missing acquisition time, size and SHA-256 as `null` until somebody actually obtains and inspects the files. Read [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md) and [docs/IMS_INGESTION.md](docs/IMS_INGESTION.md) before using local IMS files or publishing any real-data-derived material.

## Local IMS-style file ingestion (MP-009)

MotorPulse AI can inspect **local user-supplied bearing-record files** without any download or archive extraction. The adapter requires **explicit** sample rate, row count, and channel count, as none of those have been verified against the original IMS ZIP in this repository. No bearing identity, unit, time zone, window-level fault label or RUL is invented. Run against the **handwritten synthetic parser fixture**:

```bash
python -m motorpulse.ims --input-dir tests/fixtures/ims_style_synthetic \
  --test-set 2 --sample-rate-hz 8 --expected-samples 4 --expected-channels 4
```

For actual locally held IMS-like files, read [docs/IMS_INGESTION.md](docs/IMS_INGESTION.md). The installed command `motorpulse-ims` provides the same interface. **Do not commit inspected third-party raw data or derived local reports** while reuse rights remain unresolved.

## Local IMS dataset validation (MP-028)

A second offline CLI validates MP-009 inspection reports, checks chronology, sensor/channel metadata and optionally rehashes the source files. It flags possible flatlines or high-crest values for **review only**, without diagnosing a bearing fault. The Python API also supports **train-only normalization** with explicit disjoint run groups and a *native sampling-rate* Hann single-bin amplitude measurement (no resampling or g/volts conversion).

```bash
python -m motorpulse.ims_validation --report /tmp/ims-inspection.json \
  --verify-files --expected-interval-s 10 --out /tmp/ims-quality.json
```

The installed command is `motorpulse-ims-validate`. See [docs/IMS_VALIDATION.md](docs/IMS_VALIDATION.md). **All IMS-derived records and quality summaries remain local**, and original/derived redistribution rights are unresolved.

## Exploratory dataset quality reports (MP-029)

The dependency-free `motorpulse-eda` CLI generates **JSON or Markdown data-quality reports** from a verified synthetic JSONL export or locally supplied IMS inspection report. It summarizes distributions, explicit missing-data counts and first/last trend samples, while carrying forward source hashes and label caveats. The IMS mode keeps original timestamps' timezone **unknown** and never infers failure onset or RUL.

```bash
python -m motorpulse.eda --source synthetic --input datasets/demo-001 \
  --out datasets/demo-001/quality.md --format markdown
```

For a full reproducible example and the separate local-only IMS command, see [docs/EDA.md](docs/EDA.md). The report is **descriptive, not a trained predictive model**.

## Leakage-resistant split planning (MP-030)

Before fitting a future model, **split entire runs rather than randomly selecting time-adjacent rows**. The dependency-free `motorpulse-split` command builds deterministic train/validation/test plans from three or more independent synthetic-export manifests or locally held IMS inspection reports. Repeated synthetic seed/config/start groups and duplicate IMS raw-record hashes are rejected; grouping does **not** inspect held-out failure labels.

```bash
python -m motorpulse.splits --source synthetic \
  --input datasets/seed11/manifest.json datasets/seed22/manifest.json \
          datasets/seed33/manifest.json \
  --seed 42 --out datasets/group-split.json
```

The optional `--chronological --purge-ticks 4` mode is **synthetic-only**, operates on one run, and is *not* an independent-run validation. [docs/SPLITS.md](docs/SPLITS.md) explains prerequisites and leakage limitations. No data are copied, trained on or published.

## Dataset cards and provenance (MP-032)

Two packaged machine-readable cards describe the **synthetic** motor dataset and **IMS experimental source metadata** separately. They disclose contributor citation, provenance, intended/excluded uses, limitations, original data rights, simulated versus unverified labels, and leakage risks. The `motorpulse-card` CLI generates a **run-specific card** from a validated local export or IMS inspection report without downloading or publishing third-party data.

```bash
python -m motorpulse.dataset_cards --source synthetic \
  --input datasets/demo-001 --out datasets/demo-001/dataset-card.json
```

Synthetic cards include verified export-file, configuration and model-source SHA-256 digests. IMS cards leave per-window labels and RUL null and retain the **local-only redistribution HOLD**. The code's MIT license does not imply an IMS source license. See [docs/DATASET_CARDS.md](docs/DATASET_CARDS.md).

## First trained anomaly baseline (MP-010)

MotorPulse-AI now includes an **actually fitted model** for synthetic motor features: a five-feature standardized Euclidean anomaly score trained on `scenario=healthy`, `sensor_quality=good` windows **from whole training runs only**. A 99th-percentile score threshold is calibrated on that same training subset. The model refuses chronological same-run/IMS splits, source tampering or repeated run identities, and returns `null` instead of a fabricated score for missing/outlier sensor windows.

```bash
python -m motorpulse.anomaly --split datasets/baseline-split.json \
  --input datasets/baseline-11/manifest.json datasets/baseline-22/manifest.json \
          datasets/baseline-33/manifest.json \
  --preview validation --out datasets/baseline-model.json
```

Generate the three source exports and split plan first using [docs/ANOMALY_BASELINE.md](docs/ANOMALY_BASELINE.md). The installed command is `motorpulse-anomaly`. These scores are **not failure probabilities, industrial diagnostics or RUL**, and the current rule-based alerts remain a separate baseline.

## Held-out synthetic detection evaluation (MP-011)

The `motorpulse-evaluate` CLI evaluates a frozen MP-010 anomaly model on **whole-run held-out** validation or test data. It compares the trained score with existing rule-based health states on **exactly the same good-sensor windows**, separately counting missing/outlier abstentions. JSON and optional Markdown reports include TP/FP/TN/FN, precision/recall/F1, false-positive rate, score-ranked average precision, false alarms per synthetic exposure-hour, and observed fault-onset-to-first-alert delays.

```bash
python -m motorpulse.evaluation --split datasets/eval-split.json \
  --model datasets/eval-model.json \
  --input datasets/eval-11/manifest.json datasets/eval-22/manifest.json \
          datasets/eval-33/manifest.json \
  --partition test --out datasets/eval-test-report.json \
  --markdown datasets/eval-test-summary.md
```

Create the source runs, split and trained model first using [docs/EVALUATION.md](docs/EVALUATION.md). **These are simulated metrics, not real-world failure probabilities, physical lead times, RUL or industrial performance guarantees.**

## One-command reproducible synthetic ML experiments (MP-033)

The `motorpulse-experiment` CLI takes a strict JSON experiment config with **distinct generator seeds**, a fixed virtual clock, scenario assets and group split ratios. It creates a new folder containing source-hashed synthetic exports, dataset cards, whole-run split plan, **training-only learned model**, frozen held-out validation/test reports, readable Markdown summary, and artifact SHA-256 index. Existing files are never overwritten.

```bash
mkdir -p datasets
python -m motorpulse.experiment --config docs/examples/experiment-v1.json \
  --out-dir datasets/experiment-v1
```

The exporter's actual wall-clock creation timestamp is excluded only from **semantic** reproducibility hashes; the original exporter manifests keep truthful creation times. See [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md). All results are **synthetic-only** and make no real-world predictive maintenance, failure probability, or RUL claims.

## Leakage-safe feature preprocessing (MP-034)

The synthetic anomaly model now embeds a versioned `feature_processing` record with five allowlisted features, sampling and rolling-window metadata, **train-only** fitted means/scales, source-group SHA-256s and a preprocessing hash. Both preview scoring and held-out evaluation verify it before use. Shortened synthetic chronological purge gaps, repeated training windows, invalid measurements, and mismatched fitted parameters are rejected.

```bash
python -m unittest discover -s tests -p 'test_feature_pipeline.py' -v
```

See [docs/FEATURE_PIPELINE.md](docs/FEATURE_PIPELINE.md). Scores remain experimental and are not real-world failure probabilities or RUL.

## Portable and verifiable model artifacts (MP-035)

The `motorpulse-model` command saves or verifies a versioned **non-executable JSON model artifact**. It includes fitted MP-010/MP-034 model parameters, exact feature order/units, frozen train threshold, source and dataset-card references, MP-030 split membership and SHA-256 integrity metadata. **Loading for scoring requires the original split plan and local source manifests**—a bare artifact checksum is not treated as authenticity evidence.

```bash
python -m motorpulse.model_artifact verify \
  --artifact datasets/experiment-v1/model-artifact.json \
  --split datasets/experiment-v1/split-plan.json \
  --input datasets/experiment-v1/runs/seed-*/manifest.json
```

MP-033 experiments now write `model-artifact.json` and reload its verified model before evaluating. MP-011 still accepts legacy model wrappers for compatibility. See [docs/MODEL_ARTIFACTS.md](docs/MODEL_ARTIFACTS.md). The synthetic model is **not** a validated physical failure-probability or RUL estimator.

## Frozen synthetic robustness by operating regime (MP-036)

After an MP-033 experiment has completed, `motorpulse-robustness` verifies its MP-035 model artifact, original source manifests, MP-030 split, dataset cards and reproducibility index. It compares the **same frozen model and unchanged rule outputs** across held-out simulated speed, load, vibration noise/drift, fault, phase and sensor-quality conditions. It reports common-cohort confusion, AP when defined, synthetic false alarms per negative exposure hour, missing/outlier abstentions and full-track fault-alert delays.

```bash
python -m motorpulse.experiment --config docs/examples/robustness-experiment-v1.json --out-dir /tmp/mp036-run
python -m motorpulse.robustness --experiment-dir /tmp/mp036-run --partition test --out-json /tmp/mp036-test.json --out-md /tmp/mp036-test.md
```

See [docs/ROBUSTNESS.md](docs/ROBUSTNESS.md). These are **descriptive slices of programmed synthetic generator data**, not independent operating-domain trials or evidence of industrial failure risk, physical lead time or RUL. Different stress bins can have different class prevalence; no test-label tuning occurs.

## Explainable rules versus ML side by side (MP-037)

MP-037 runs a **source-verified, frozen** rules/model comparison on complete MP-033 held-out source runs. It checks that overall and per-run metrics exactly match MP-011 and that both methods abstain for missing/outlier sensor windows. Reports include nine mutually exclusive outcomes (model-only / rules-only / shared alerts and mistakes), deterministic bounded concrete examples, the original rule threshold checks and five training-scaled feature contributions that numerically reproduce the anomaly score. Contributions are *not causal fault explanations*.

```bash
python -m motorpulse.experiment --config docs/examples/robustness-experiment-v1.json --out-dir /tmp/mp037-experiment
python -m motorpulse.comparison --experiment-dir /tmp/mp037-experiment --partition test --max-examples 4 --out-json /tmp/mp037-test.json --out-md /tmp/mp037-test.md
```

See [docs/COMPARISON.md](docs/COMPARISON.md). Results remain **synthetic-only** and are not industrial detection rates, maintenance advice, physical failure probabilities or RUL.

## Validation-only anomaly threshold calibration (MP-038)

The `motorpulse-calibrate` CLI chooses a **separate, validation-only decision threshold** for the frozen MP-010 synthetic anomaly score under a chosen *empirical validation false-positive-rate budget*. Original MP-035 model parameters, training-only threshold, processor and grouped split are immutable. Source and experiment file hashes are checked. **Test labels are first read after the threshold is chosen**; original and selected thresholds are compared on the same eligible sensor-good test windows, with original rules unchanged.

```bash
python -m motorpulse.experiment --config docs/examples/robustness-experiment-v1.json --out-dir /tmp/mp038-exp
python -m motorpulse.calibration --experiment-dir /tmp/mp038-exp --target-fpr 0.05 --out-json /tmp/mp038-report.json --out-md /tmp/mp038-report.md
```

The report contains a validation-only operating-point tradeoff curve, explicit allowed/achieved validation false-alarm counts, held-out synthetic test metrics, source/processor/model fingerprints and abstention counts. An empirical validation FPR **does not guarantee future or real-world alarm rates**, physical failure probability, diagnosis or RUL. See [docs/CALIBRATION.md](docs/CALIBRATION.md).

## RUL research: failure evidence and censoring gate (MP-039)

**RUL is not supported as a prediction.** MP-020 scheduled synthetic fault onset, anomaly scores and alert delays do not reveal machine end-of-life. MP-039 introduces a standalone, metadata-only research contract that checks terminal-event timestamps versus right-censoring, source and annotation review states, consistent UTC observation times, and physical-asset-disjoint train/validation/test groups. It explicitly blocks fictional synthetic labels and treats even apparently complete *self-reported* observational evidence as requiring independent external review. **It never fits a model, estimates remaining life, certifies a license or authorizes training.**

```bash
python -m motorpulse.rul_research --protocol docs/examples/rul-protocol-v1.json --out-json /tmp/mp039-audit.json --out-md /tmp/mp039-audit.md
```

The shipped example is **fabricated research-contract metadata** and intentionally yields `blocked`. See [docs/RUL_RESEARCH.md](docs/RUL_RESEARCH.md) for failure definitions, informative censoring, prospective IPCW/concordance metrics, field-evidence prerequisites and leakage controls.

## Durable local SQLite telemetry and rule-alert history (MP-012)

MotorPulse-AI now supports **opt-in** SQLite storage of the complete simulated feature snapshot, each motor event and illustrative good-sensor rule warning/critical decisions. One transaction commits a full tick; failed writes never advance the live simulator. Restart, reset and scenario configuration create **distinct persistence sessions**, preserving previous history and deterministic replay. No database is created in the memory-only default.

```bash
python -m motorpulse --paused --database ./motorpulse-local.sqlite3
```

The existing live API remains backward compatible. When persistence is enabled, `/api/status` additionally reports the session ID and storage health; historical data is queryable through bounded, parameterized Python storage/controller methods. **HTTP history endpoints are MP-040, trend charts MP-013, and alert lifecycle deduplication MP-042.** Stored alarms are only synthetic rule evaluations, not physical fault diagnoses. See [docs/SQLITE_HISTORY.md](docs/SQLITE_HISTORY.md).

## SQLite history and event REST endpoints (MP-040)

With MP-012 SQLite persistence enabled, MotorPulse now exposes **read-only**, localhost-only historical queries for sessions, snapshots, individual motor telemetry and simulated rule alerts, with bounded paging and optional sensor/asset/UTC time filters. Invalid queries, disabled storage and unavailable database reads have explicit documented JSON errors. A history GET never advances the simulator.

```bash
python -m motorpulse --paused --database ./motorpulse-local.sqlite3
# then visit http://127.0.0.1:8765/api/history/events?asset_id=MTR-01&limit=20
```

`GET /api/history/sessions`, `/snapshots`, `/events`, and `/alerts` return versioned result envelopes with stable `before_id` cursors. UTC start/end filters preserve even **microsecond-resolution virtual ticks**. Source events are synthetic-only and rule alerts are not field diagnoses. See [docs/HISTORY_API.md](docs/HISTORY_API.md) for precise filters, response shapes, error codes and examples; dashboard historical charts and alert lifecycle remain MP-013 and MP-042.

## Dashboard simulation controls and clock settings (MP-041)

The localhost dashboard supports **validated runtime seed and time controls**,
alongside existing Start/Pause/Step/Reset, fault progression, severity, simulated RPM variability and load/noise controls.
Users can edit the deterministic seed, **virtual seconds per tick** and distinct **real wall-clock update interval**.
Applying runtime settings atomically resets the simulator to a paused tick 1. Optional SQLite persistence begins a new recording session while preserving old history.
Active settings and simulated UTC are clearly labelled; numeric fields have accessible labels, boundaries and status messages.

```bash
python -m motorpulse --paused --database ./motorpulse-local.sqlite3
# Edit settings in the dashboard or use PUT /api/runtime
```

The strict local API accepts exactly seed, step_seconds and interval_seconds, and reports 400/409/503 for invalid/busy-storage cases.
See [docs/RUNTIME_CONTROLS.md](docs/RUNTIME_CONTROLS.md) for the full clock, validation, replay, persistence and accessibility contract.
No hardware speed setpoint or field prognostics are supported.
## Historical trend dashboard (MP-013)

With optional MP-012 SQLite storage, the existing localhost dashboard now displays **recorded synthetic vibration RMS (g), temperature (°C) and RPM trends**. Select a past recording session, motor and inclusive virtual UTC range; browse older/newer bounded pages. An expandable accessible numerical table accompanies three responsive SVG charts. Missing/suspect vibration points create gaps rather than interpolated synthetic readings.

```bash
python -m motorpulse --paused --database ./motorpulse-local.sqlite3
# Open http://127.0.0.1:8765/ and scroll to Recorded synthetic trends
```

History is disabled by default while the live simulator still works. The offline-bundled chart script uses no CDN or third-party dependency. See [docs/HISTORICAL_DASHBOARD.md](docs/HISTORICAL_DASHBOARD.md) for source, filtering, quality and accessibility limitations.



To limit GitHub Actions usage, tests run automatically on pull requests targeting `main` (not separately for feature pushes or merge pushes); manual runs remain available. Run `python -m unittest discover -s tests -v` locally first.

## Persistent synthetic rule incidents and review (MP-042)

Optional local SQLite history now groups consecutive **synthetic rule warning/critical ticks** into deduplicated per-motor/per-session incidents while preserving every original raw alert and telemetry event. Incidents track severity/reason changes, good-sensor resolution and an **interrupted** state for missing/suspect vibration. SQLite v3 migrates earlier recordings transactionally.

The historical dashboard shows a **Synthetic rule incidents** table, recent changes and a deliberate once-only reviewer label. Review is unauthenticated, recorded with separate real UTC time and **does not imply physical maintenance or safety**. Local endpoints include GET /api/history/incidents, GET /api/history/transitions and POST /api/incidents/acknowledge. See [docs/ALERT_LIFECYCLE.md](docs/ALERT_LIFECYCLE.md).

```bash
python -m motorpulse --paused --database ./motorpulse-local.sqlite3
```

## Planned engineering work
1. Add configurable fault fixtures and labelled synthetic datasets.
2. Import publicly available NASA IMS bearing data *after confirming its reuse terms*; do not commit third-party data dumps.
3. Train and evaluate classical anomaly detectors against a reproducible baseline.
4. Add model cards, confusion matrices, robustness tests and clear failure modes.
5. Add persistent event storage, authenticated APIs, streaming, then hardware adapters in a **later, separate phase**.

## Safety and limitations
These scores are **not** validated failure probabilities or remaining useful life predictions. This demonstration is not industrial condition-monitoring equipment. Simulated data cannot establish real-world ML accuracy; independent field validation will be required.

## References
- NASA IMS bearings: https://data.nasa.gov/dataset/ims-bearings
- NASA Prognostics data repository: https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/

MIT-licensed software. See `LICENSE` and `CONTRIBUTING.md`.
