# MP-034 — Leakage-safe feature preprocessing and time-window guards

MotorPulse-AI's first ML model is trained only on **synthetic** motor events. All learned scaling parameters are fitted on **training only**; validation/test labels or feature values must never enter those estimates. This explicit boundary prevents **data leakage** between experiment partitions. MP-034 formalizes its preprocessing boundary: **the transformations are fitted on healthy, sensor-good training runs only**, recorded in a versioned, source-linked artifact, and independently verified before validation/test scoring. There is **no physical machine calibration, failure probability, RUL, cloud inference or real bearing diagnosis**.

## 1. Fixed feature allowlist

The v1 contract contains **exactly five input features**, all computed from each simulated event:

| Feature | Units | Scientific caution |
|---|---|---|
| `rms_g` | vibration g RMS | Synthetic acceleration, not field-calibrated |
| `crest_factor` | dimensionless | Spikes may reflect simulation artifacts |
| `band_80_400_rms_g` | vibration g RMS | Frequency-band definition tied to 1024 Hz example |
| `temperature_c` | degrees C | Simulation load/fault coupling is programmed |
| `rpm` | rev/min | Changing operating regimes can trigger anomalies |

Fields **excluded from the model vector** include `scenario`, `severity`, `fault_phase`, `configured_scenario`, `configured_severity`, `sensor_quality`, `health`, `reasons`, `asset_id`, `event_id`, `export_id`, `source`, `tick`, timestamps, operating configuration, and `load_factor`. These can be used for **training eligibility, provenance or evaluation**, but never as numerical predictors or normalization inputs. No feature ranking is learned from held-out labels.

The sampling contract is **1024 acceleration samples at 1024 Hz**, a **1-second nominal waveform window**, and a **5-tick rolling history**, with legitimate rolling observation/valid counts. Unsupported sampling schemes, nonfinite/negative model features, invalid tick/history metadata and wrong sample counts are rejected. These synthetic units must **not** be applied to unknown-rate/unknown-unit original IMS experiments.

## 2. Training-only fitted transformations

`motorpulse.feature_pipeline.fit_preprocessing` requires explicit `train_groups`, a complete whole-run MP-030 split SHA-256, per-group verified source file hashes and rows already selected as **`scenario="healthy"` and `sensor_quality="good"`**. It rejects a row carrying a validation/test group, duplicate run/asset/tick identity, invalid training truth or sensor state, malformed hashes, and training cohorts smaller than eight eligible windows.

For every allowlisted feature, compute the **training-only population mean**, population standard deviation, and effective scale:

```text
mean_j    = mean(x_j over eligible training events)
std_j     = sqrt(mean((x_j - mean_j)^2 over eligible training events))
scale_j   = max(std_j, 0.01 * abs(mean_j), 0.000001)
z_j       = (x_j - mean_j) / scale_j
score(x)  = sqrt(sum_j(z_j^2) / 5)
```

The existing MP-010 healthy-trained standardized Euclidean detector retains this exact method and training-only in-sample **99th-percentile** score threshold. The floor is a numerical choice, not an uncertainty estimate. The processor does **not** use global imputation, dynamic feature selection, clipping, test-informed threshold adjustment or covariance estimates. The model and original uncalibrated health rules remain separate.

A fitted model now embeds `feature_processing` with:

- `pipeline_version="1.0.0"`, fixed feature names/units/excluded fields and sampling/rolling contract.
- `fit_partition="train"`, sorted complete training group IDs, split-plan SHA-256, **source-data SHA-256 per training group**, and training-window count.
- Means, population standard deviations and effective scales, with unchanged MP-010 decision scoring.
- Explicit missing/outlier, feature-selection and normalization policies, and a canonical `pipeline_sha256`.

Before either `motorpulse.anomaly.score_partition` or `motorpulse.evaluation.evaluate`, the system **checks the fitted pipeline digest**, training-run source hashes, current split-plan identity, feature contract, and that fitted parameters match the model's own parameters and eligible training-window count. An altered data source, source group assignment or recomputed model SHA alone cannot silently bypass these consistency checks.

**No validation/test values enter fitting.** Model evaluation continues to return **null/unscorable** for missing or outlier sensor windows, and both rules and learned anomalies use the same good-sensor cohort. A sensor-quality *injection label* gates scoring only; it is not a learned feature.

## 3. Overlapping waveform and rolling-window boundaries

Two synthetic time dependencies deserve distinct treatment:

1. A single per-tick waveform is nominally **1 second**. If the virtual tick interval is shorter than this, adjacent waveform time windows nominally overlap. Their simulator-generated samples are not proven to be independent physical acquisitions.
2. The rolling RMS/temperature diagnostic includes up to **five prior/current ticks**. If these are split across training and test, feature history can leak measurements between partitions.

**Primary ML evaluation** continues to use MP-030 **complete independent generator-run groups**, never a row-level random split. All motors, timestamps and rolling-history features within one run remain in the **same** partition; repeated seed/config/clock run fingerprints are rejected.

MP-030's optional **synthetic-only exploratory chronological** holdout uses explicit inclusive tick ranges and two purge ranges. MP-034 now independently validates actual range gaps, the advertised purge metadata, and the minimum gap:

```text
required_discarded_ticks =
    max(rolling_lookback_ticks - 1,
        ceil(waveform_window_seconds / virtual_step_seconds))
```

The default 1.5-second step requires **4 discarded ticks**; a 0.1-second virtual step requires at least **10**. Forged or shortened gaps and inconsistent boundary metadata raise errors. A correctly purged chronological split is **still not permitted for MP-010 training**: runs share a generator and their operating context is correlated. Purging mitigates specific adjacent-window dependencies, not all forms of temporal dependence or model generalization bias.

## 4. Reproducible experiment integration

MP-033's existing one-command workflow now persists the fitted feature processor inside `trained-model.json`, and records its **SHA-256 and version** in `experiment-index.json` and `SUMMARY.md`.

```bash
mkdir -p datasets
python -m motorpulse.experiment \
  --config docs/examples/experiment-v1.json \
  --out-dir datasets/experiment-with-features
```

The experiment source is only **synthetic**, with MP-032 run cards and MP-030 source-verified splits. The model is fit from authorized training run windows alone; MP-011 validation/test metrics use **frozen preprocessing and frozen threshold**. Stable artifacts are checksummed as before, while raw exporter manifests keep truthful (volatile) creation timestamps, excluded only from *semantic* manifest digests.

For a direct view:

```python
import json
from pathlib import Path
base = Path("datasets/experiment-with-features")
model = json.loads((base / "trained-model.json").read_text())["model"]
index = json.loads((base / "experiment-index.json").read_text())
pipeline = model["feature_processing"]
assert pipeline["pipeline_sha256"] == index["feature_pipeline_sha256"]
assert pipeline["fit_partition"] == "train"
assert pipeline["train_groups"] == model["training"]["groups"]
```

## 5. Regression checks and limitations

```bash
python -m unittest discover -s tests -p 'test_feature_pipeline.py' -v
python -m unittest discover -s tests -v
```

MP-034 adds **19** regression tests: feature exclusion, missing/nonfinite inputs, sample/window contract, population statistics and scale floors, replay, source-group contamination, duplicate training windows, bad truth/sensor selection, corrupted model/source fingerprints, unchanged held-out model parameters, safe purge metadata and fast-window overlap geometry, and integration with MP-033 artifacts.

The tests use generated synthetic events and local fixtures only. No third-party IMS archive or derived samples are imported or committed. The resulting model remains a **small educational baseline**; feature decorrelation, imputation learned from training data, representation drift detection, uncertainty calibration and physically independent held-out machines are future work. Neither synthetic precision/recall nor detection delay validates real maintenance lead time, **failure probability, or RUL**.
