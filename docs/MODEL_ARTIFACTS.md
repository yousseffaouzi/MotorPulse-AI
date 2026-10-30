# MP-035 — Portable, versioned model artifacts

MotorPulse-AI can now save, load and verify the **first trained, synthetic-only healthy anomaly detector** in a **non-executable, strict JSON model artifact**. The purpose is to make experiments auditable and model reuse *fail closed* when the feature contract, train-only preprocessing, source runs or MP-030 split no longer match. Fitted transformations use **training only**; held-out measurements must not update the saved model or its threshold.

**This is not a calibrated industrial model**: anomaly scores are unusualness relative to scripted synthetic training data, not a physical failure probability, validated maintenance warning or **RUL** estimate. No original or derived IMS experimental data are included; the IMS licensing/redistribution review remains on hold.

## 1. Generate and reload an artifact

Run the [MP-033 experiment](EXPERIMENTS.md) as usual:

```bash
mkdir -p datasets
python -m motorpulse.experiment \
  --config docs/examples/experiment-v1.json \
  --out-dir datasets/portable-demo
```

The output now contains both `trained-model.json` (legacy API-compatible wrapper) **and** `model-artifact.json` (strict MP-035 portable artifact). The index and `SUMMARY.md` record provenance; `experiment-index.json` includes `model_artifact_version`, `model_artifact_sha256`, and the **exact-byte SHA-256** for `model-artifact.json`.

To create a portable artifact from an existing MP-010 model and original MP-030 source manifests:

```bash
python -m motorpulse.model_artifact save \
  --split datasets/portable-demo/split-plan.json \
  --model datasets/portable-demo/trained-model.json \
  --input datasets/portable-demo/runs/seed-0000000011/manifest.json \
          datasets/portable-demo/runs/seed-0000000022/manifest.json \
          datasets/portable-demo/runs/seed-0000000033/manifest.json \
          datasets/portable-demo/runs/seed-0000000044/manifest.json \
          datasets/portable-demo/runs/seed-0000000055/manifest.json \
  --out datasets/standalone-model-artifact.json
```

The installed command is `motorpulse-model`. Existing output files are never overwritten.

**Verify a saved model before scoring:**

```bash
python -m motorpulse.model_artifact verify \
  --artifact datasets/portable-demo/model-artifact.json \
  --split datasets/portable-demo/split-plan.json \
  --input datasets/portable-demo/runs/seed-0000000011/manifest.json \
          datasets/portable-demo/runs/seed-0000000022/manifest.json \
          datasets/portable-demo/runs/seed-0000000033/manifest.json \
          datasets/portable-demo/runs/seed-0000000044/manifest.json \
          datasets/portable-demo/runs/seed-0000000055/manifest.json
```

Verification reads **all local source manifests** and rechecks source JSONL hashes/bytes, run groups, dataset cards, MP-030 split, MP-034 fitted preprocessing, and frozen model parameters. It never retrains, recalibrates or downloads a dataset.

MP-011's evaluator now accepts the portable artifact directly with its existing `--model` argument (and still accepts legacy `{"model": {...}}` documents). `evaluate()` and `score_partition()` continue accepting a verified in-memory model; for a saved file, call `load_model_artifact` first:

```python
import json
from pathlib import Path
from motorpulse.model_artifact import load_model_artifact
from motorpulse.evaluation import evaluate

base = Path("datasets/portable-demo")
plan = json.loads((base / "split-plan.json").read_text())
manifests = sorted((base / "runs").glob("seed-*/manifest.json"))
model = load_model_artifact(base / "model-artifact.json",
                            plan=plan, manifests=manifests)
report = evaluate(plan, manifests, model, partition="test")
print(report["overall"]["model"]["precision"])
```

The loader returns a separate in-memory model copy after verifying source provenance. It does not turn the JSON content into executable Python code.

## 2. Portable JSON schema and compatibility

The v1 artifact (`artifact_version="1.0.0"`) has **strict, exact top-level fields**. Important ones include:

| Field | Contract |
|---|---|
| `artifact_version`, `kind` | Versioned JSON layout; unexpected versions/kinds rejected |
| `algorithm`, `model_version` | Fixed MP-010 healthy-training standardized Euclidean method |
| `model`, `model_sha256` | Complete immutable-by-policy training model and canonical numeric-parameter hash |
| `feature_contract` | Ordered five numeric features, units, 1024 Hz / 1024 samples, absent/outlier policies |
| `processor_sha256` | MP-034 training-only fitted feature processor digest; full processor also embedded in model |
| `split_plan_sha256`, `training_groups` | Source-run split identity and complete set of training groups |
| `source_runs` | Sorted, path-free per-run group IDs, source data/config/model-code SHA-256, MP-032 dataset-card IDs and train/validation/test membership |
| `runtime` | Python major/minor series and implementation, producer source SHA-256, no runtime dependencies, portability warning |
| `artifact_sha256` | Canonical digest of all artifact fields except itself; tampering detection, **not a signature** |

There is **no pickle, eval, arbitrary dynamic import, executable model graph or downloaded code**. Loading uses the existing strict UTF-8 JSON parser: duplicate keys and nonfinite JSON values are refused; files must be regular, non-symlinked, and **no larger than 512 KiB**. Saving a model is exclusive-create, with a rollback of the newly created partial file on a write failure.

The loader rejects changed feature order/units/sampling, missing/negative/infinite coefficients, zero or negative scales, altered training-only 99th-percentile threshold, incompatible model/processor values, invalid source cardinalities, and unrecognized future versions. A copied file containing a recomputed self-check hash is **still rejected** if it differs from the supplied original source/plan identity.

File hashes only demonstrate **bit-level integrity against supplied references**, not the scientific accuracy or provenance authenticity of a dataset. They are not signatures, legal reuse permissions or protection against a malicious adversary who controls both data and reference hashes.

## 3. Training-only, reproducibility and leakage limits

- The embedded feature processor records exactly the training groups, their source digests, **healthy + sensor-good eligibility count**, means, population deviations and engineering scale floors. Feature identities and fixed exclusion list prevent fault truth, rule outputs, source IDs or timestamps from silently entering the model vector.
- Repeated generator runs are rejected by the split planner. Validation and test groups are **not** used to fit normalization, thresholds or feature selection. Missing/outlier sensor windows remain **unscorable**.
- The source-run metadata includes MP-032 dataset-card identities and code/config provenance. **Real IMS bearing labels remain unverified**, and original/derived archive redistribution is not authorized by NASA hosting alone.
- Artifacts include no absolute source paths and no volatile wall-clock creation time. Given the same inputs, producer code, implementation and Python **major/minor** runtime, the artifact bytes are designed to replay deterministically independent of output path, input manifest order, and Python patch-level upgrades within that series. Cross-major/minor floating-point equality is **not guaranteed**; runtime/source code provenance is recorded for review.
- MP-033 experiments retain their legacy `trained-model.json` for compatibility. A loaded artifact is verified **before** MP-011 evaluation; the shared anomaly-vs-rule eligibility policy is unchanged.

## 4. Regression checks

```bash
python -m unittest discover -s tests -p 'test_model_artifact.py' -v
python -m unittest discover -s tests -v
```

The original **19 MP-035 tests** cover strict save/load replay, path-independent reproducibility, source validation after file changes, split mismatch, unsupported versions, source-card forgery, model/processor tampering (including recomputed checksums), invalid units/coefficients/threshold, JSON parser rejection, size limits, non-overwrite, installed CLI and MP-033/MP-011 integration. MP-056 adds a focused regression proving that two patch releases in the same Python major/minor series produce the same portable artifact and artifact SHA.

All tests use synthetic MotorPulse exports created in temporary directories. This is software research tooling, **not** validation for real rotating machinery or physical Remaining Useful Life prediction.

**Next:** MP-036 tests robustness across speed, load, noise and synthetic fault strengths; MP-037 provides focused rules-vs-ML explanations and false-positive examples.