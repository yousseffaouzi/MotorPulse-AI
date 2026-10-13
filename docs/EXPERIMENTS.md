# MP-033 — Reproducible synthetic ML experiments

**Purpose:** one offline command orchestrates MotorPulse-AI's existing verified software-first pipeline, without downloading data or assuming any industrial diagnostic capability. MP-033 uses only the Python standard library (Python 3.11+) and **synthetic motor feature events**. IMS experimental archive records, IMS-derived data, and real-world fault-onset labels are **not** used.

The orchestration reuses:
- MP-008 **source-hashed synthetic export**, one complete generator run per seed.
- MP-032 **versioned source-bound dataset cards** for every run.
- MP-030 **label-blind whole-run train/validation/test splits**, including duplicate-run checks.
- MP-010 **healthy-good-sensor training-only** standardized-distance model and a frozen training-only 99th-percentile threshold.
- MP-011 **held-out validation and test** evaluation, with shared rule/model denominators, PR average precision, precision, recall, F1, FPR, sensor abstentions and scripted synthetic fault-episode delays.

## Run the example

From the repository root, where a new `datasets/` directory already exists:

```bash
mkdir -p datasets
python -m motorpulse.experiment \
  --config docs/examples/experiment-v1.json \
  --out-dir datasets/experiment-v1
```

The installed command is `motorpulse-experiment`. The example is in [docs/examples/experiment-v1.json](examples/experiment-v1.json). Edit it to select your scenario mix, distinct seeds, virtual start time, tick duration and split ratios. **Use a fresh output directory** for every run. Nothing is overwritten.

The configuration is one strictly parsed UTF-8 JSON object containing **exactly**:

| Field | Meaning / constraints |
|---|---|
| `experiment_version` | `"1.0.0"` |
| `seeds` | 3–12 distinct unsigned 32-bit integer seeds, sorted internally |
| `ticks` | 8–1000 simulated ticks *per run* |
| `assets` | A complete `{"assets":[...]}` object, validated as MP-007/MP-020 scenarios; no external file paths |
| `virtual_start_utc` | ISO 8601 instant with explicit UTC zone |
| `step_seconds` | Finite positive virtual step in microsecond increments, up to 86400 |
| `split_seed` | Unsigned 32-bit integer controlling deterministic, **label-blind** whole-run assignment |
| `split_ratios` | Exactly three positive proportions summing to 1, assigned **by whole runs**, not by individual rows |

Unknown configuration fields, duplicate JSON keys, nonfinite numbers, URL/path injections, duplicate seeds, non-UTC times and invalid motor scenario schedules are rejected. It never loads code, secrets or arbitrary file paths specified in the experiment JSON. For a complete schema of motor attributes see [the scenario configuration guide](CONFIG_FILE.md) and [model assumptions](MODEL_ASSUMPTIONS.md).

## Output layout

The output directory is claimed with atomic exclusive creation. On failure, only the directory created by that invocation is cleaned; an existing user-owned path is **never touched**.

```text
experiment-v1/
  experiment-config.json
  experiment-index.json
  split-plan.json
  trained-model.json
  model-artifact.json
  validation-metrics.json
  test-metrics.json
  SUMMARY.md
  runs/
    seed-0000000011/
      events.jsonl
      manifest.json
      dataset-card.json
    seed-0000000022/
      events.jsonl
      manifest.json
      dataset-card.json
    ... (one folder per seed)
```

The index contains the normalized configuration digest, Python interpreter/version and implementation, a SHA-256 of `motorpulse/experiment.py`, dataset card IDs, each run's source-data digest, split-plan digest, model digest, **MP-035 portable model artifact digest/version**, **MP-034 versioned train-only preprocessing SHA-256**, train and held-out group identities, and SHA-256 checksums of **stable output file bytes**. Each evaluation has its own content hash and source-run traceability. `SUMMARY.md` is a concise reader-friendly overview of validation/test metrics and explicit scientific disclaimers.

For integrity auditing of stable files:

```python
from pathlib import Path
import hashlib
import json
folder = Path("datasets/experiment-v1")
index = json.loads((folder / "experiment-index.json").read_text())
for relative, expected in index["stable_artifact_sha256"].items():
    actual = hashlib.sha256((folder / relative).read_bytes()).hexdigest()
    assert actual == expected, relative
```

The manifest itself uses `experiment_sha256`, calculated from all its other canonical fields. This is an integrity fingerprint, **not a cryptographic signature**.

### Important reproducibility distinction

The underlying MP-008 exporter intentionally stores an **actual wall-clock** `created_at_utc` inside each per-run `manifest.json`. That timestamp is a truthful export audit field and can change even when the data are bit-identical. MP-033 therefore:
1. Uses **exact SHA-256** for `events.jsonl`, dataset cards, split plan, model, evaluated reports, configuration and summary;
2. Records a separate `source_manifest_semantic_sha256` for each export manifest, computed from its parsed content **excluding only `created_at_utc`**;
3. Does **not** claim the original raw `manifest.json` byte hash is the semantic digest.

With the same source code, Python version, configuration and seed set, stable artifact bytes and metrics are designed to reproduce even when input seed order or output location changes. The system records Python version/implementation and experiment orchestrator source hash; **cross-version floating-point identity, low-level runtime compatibility and machine-independence are not certified**. There is currently no pinned third-party runtime dependency because the project intentionally uses the standard library only. Frozen binary environments and formal versioned model packaging remain future work.

## Evaluation methodology and data leakage

**Train, validation and test always use disjoint complete generator runs.** All assets/windows within a run stay together. The split routine rejects repeats of the same seed/config/virtual-clock generator source under altered tick lengths. The orchestrator supplies every source manifest to each stage; trained parameters and threshold are fitted using only *healthy* and *sensor-good* training windows. The evaluation stages check that model source identities and group assignments match the split and refuse test-label tuning or refitting.

MP-035 now packages a [strict, source-verified portable model artifact](MODEL_ARTIFACTS.md) alongside the legacy trained-model wrapper, reloads it against the complete split/source manifests and evaluates using the verified frozen model. Validation and test use the **same frozen model, MP-034 fitted feature processing and threshold**. The [feature preprocessing contract](FEATURE_PIPELINE.md) records feature units, training-only source hashes and the sampling/rolling-window geometry; both scoring paths verify it before use. The original heuristic health rules and new anomaly decisions are scored on identical good-sensor held-out events. Missing and synthetic outlier sensor windows are listed separately as abstentions rather than classified as healthy. Undefined metrics remain JSON `null`.

Anomalies and fault delays represent responses to **scripted synthetic truth**. They do **not** establish an industrial false alarm rate, physical maintenance lead time, calibrated **failure probability** or **RUL**. Distinct random seeds do not turn a shared simulation generator into independently validated real-world machines.

### Local checks

```bash
python -m unittest discover -s tests -p 'test_experiment.py' -v
python -m unittest discover -s tests -v
```

MP-033 adds 16 automated tests covering valid/invalid configurations, source ownership and path safety, byte-stable source/result hashes, reordered seeds, no overwrite, interrupted-run cleanup, insufficient healthy records, full held-out model/metric provenance, CLI and docs. They generate all source data locally from the simulator; no IMS archive or third-party material is downloaded, inspected or committed.

**Next:** MP-034 train-only preprocessing and MP-035 portable model artifacts are implemented; MP-036 operating-regime robustness and MP-037 interpretability/rules-vs-ML experiments follow.

## MP-037 explanatory comparison reports

After creating the versioned MP-033 experiment, you can produce a post-hoc side-by-side breakdown with the command in [COMPARISON.md](COMPARISON.md). It re-verifies the original MP-035 artifact and complete source index, then samples deterministic, clearly nonrepresentative explanatory examples from the frozen MP-011 held-out model and rules. No extra experiment setting or retraining is required.

## MP-038: validation-only threshold calibration

Use the existing complete MP-033 output directory with the offline `motorpulse-calibrate` command from [CALIBRATION.md](CALIBRATION.md) to select a separate target-FPR operating point from **validation only** and report its performance on the untouched held-out test. The MP-035 original model file, source index and train-only preprocessing stay immutable; original MP-011 rule/model benchmark files remain unchanged. Empirical simulated FPR has no industrial reliability guarantee.
