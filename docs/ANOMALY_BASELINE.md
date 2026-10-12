# MP-010 — Healthy-trained anomaly-detection baseline

**Status:** first genuinely fitted, reproducible **synthetic-only** machine-learning baseline. This is an educational multivariate anomaly score trained on healthy *simulated* feature events. It is **not** a calibrated industrial failure probability, remaining useful life (RUL), real hardware diagnosis or a replacement for maintenance inspection.

There is no external ML dependency. The implementation uses Python 3.11+ standard-library statistics and explicitly recorded training-only model parameters. Its conservative evaluation boundary is the [MP-030 whole-run split](SPLITS.md), and the dataset provenance comes from [MP-032 cards](DATASET_CARDS.md).

## Reproducible example — three complete simulated runs

From the repository root:

```bash
mkdir -p datasets

python -m motorpulse.export --out-dir datasets/baseline-11 \
  --seed 11 --ticks 30 --format jsonl
python -m motorpulse.export --out-dir datasets/baseline-22 \
  --seed 22 --ticks 30 --format jsonl
python -m motorpulse.export --out-dir datasets/baseline-33 \
  --seed 33 --ticks 30 --format jsonl

python -m motorpulse.splits --source synthetic \
  --input datasets/baseline-11/manifest.json \
          datasets/baseline-22/manifest.json \
          datasets/baseline-33/manifest.json \
  --seed 42 --out datasets/baseline-split.json

python -m motorpulse.anomaly \
  --split datasets/baseline-split.json \
  --input datasets/baseline-11/manifest.json \
          datasets/baseline-22/manifest.json \
          datasets/baseline-33/manifest.json \
  --preview validation --out datasets/baseline-model.json
```

The installed command is `motorpulse-anomaly`. Output files must be **new** (never overwrite existing data). The output JSON contains `model` and a bounded `preview` of the chosen partition. A preview is **not an evaluation scorecard**; MP-011 will introduce proper false-alarm and detection statistics. No network services, original IMS data, raw waveforms or real-data-derived features are used.

The CLI requires **all** manifests listed in the split plan so it can verify global source membership, detect groups omitted or repeated across train/validation/test, and reject drift in data or configuration. It **does not** fit on all supplied manifests: only `partitions.train.group_ids` are iterated by the fitting routine. Non-training sources are integrity-validated but their **feature measurements, labels and health states do not contribute** to model centers, scales or decision threshold.

## Training and mathematics

The v1 feature contract is a **fixed allowlist** of five continuous synthetic fields, already exported by MP-008:

| Feature | Units | Included? |
|---|---|---|
| `rms_g` | g RMS | Yes |
| `crest_factor` | dimensionless | Yes |
| `band_80_400_rms_g` | g RMS | Yes |
| `temperature_c` | degrees Celsius | Yes |
| `rpm` | RPM | Yes |
| `scenario`, `severity`, `configured_scenario`, `fault_phase` | synthetic label/config | **No** |
| `health`, `reasons` | baseline rule outputs | **No** |
| `sensor_quality` | injected sensor state | **No** — used only to screen out invalid windows |
| `asset_id`, `event_id`, `source`, `timestamp_utc` | identity/time | **No** |

The programmed synthetic `scenario == "healthy"` acts as a **training eligibility label**, not a numeric input feature. The training subset is all windows with `scenario == "healthy"` **and** `sensor_quality == "good"`, exclusively within the **training** complete source runs. Other faults or unhealthy sensor intervals are excluded from parameter fitting; the model requires at least **8 eligible windows** and refuses silently training on unknown/IMS labels.

For feature `j`, fitted population mean and deviation use **training values only**:

```text
μ_j      = mean(x_j over healthy, good-sensor training windows)
σ_j      = sqrt(mean((x_j - μ_j)^2 over those windows))
scale_j  = max(σ_j, 0.01 × abs(μ_j), 0.000001)
z_j      = (x_j - μ_j) / scale_j
score(x) = sqrt((1/5) × Σ_j (z_j)^2)
```

The **1% center-based scale floor** is a documented numerical engineering choice for near-constant synthetic features—not a calibrated measurement uncertainty. The method is a diagonal, standardized Euclidean distance: it does **not** model covariance or learn nonlinear vibration dynamics. A larger score means **more unusual relative to the learned synthetic baseline**, not “more likely to fail.”

A decision boundary is the empirical **99th percentile** of training-healthy scores (linearly interpolated). A valid score **strictly greater** than that threshold receives `anomaly`; other scored events receive `within_training_threshold`. **This in-sample threshold is not a guaranteed 1% false-positive rate** on held-out simulated motors or any physical motor.

### Sensor-quality gating

Measurements marked `sensor_quality="missing"` or `"outlier"` are **not scored**: they receive `anomaly_score: null` and `decision: "unscorable"`, with a separate missing-sensor / sensor-outlier count. A zero score is **not** substituted for missing vibration. The model does not learn to identify defective sensors independently; `sensor_quality` reflects a *known synthetic injection*.

The existing rule-based `health` output is displayed separately in previews for transparency, but **does not affect training, model scoring, calibration or classification**. Comparisons with a common held-out metric definition and false-positive examples are planned for MP-011 and MP-037.

## Split enforcement and data leakage

The trained baseline requires **`policy="whole_run_grouped"`** and `source_type="synthetic_motor_feature_events"`. It intentionally rejects:

- MP-030's **same-run chronological** mode; that mode is useful for exploration, but not independent-run fitting of this baseline.
- IMS source runs: original archive-specific labels, sampling units and redistribution rights have not been verified.
- Split-plan checksum mismatches, missing planned runs, group overlap between partitions, repeated seed/config/start source groups, changed source-file digests, or inconsistent source IDs and record counts.
- Training with too few healthy, good-sensor records; nonfinite/negative features or unrecognized sensor data.

The result records training **group IDs**, synthetic dataset-card identities, data-source/config/model-code hashes, feature contracts and explicit `fit_partitions=["train"]`. The model SHA-256 is a reproducibility fingerprint of the complete fitted numeric parameters and provenance, **not a digital signature or proof of model validity**.

All healthy-window selection, preprocessing/scaling and threshold calibration occur only on the **training** partition. The model is not updated when validation/test data are scored. A stored model can later be validated against its own source-linked split plan, but the MP-010 CLI is deliberately a small reproducible demo rather than the full experiment/artifact manager planned for MP-033 and MP-035.

## Scientific limitations

- Synthetic fault amplitudes and healthy conditions are predetermined generator assumptions. Independent random seeds do not prove generalization to **real machines** or to unmodeled regimes.
- Grouping complete simulator runs helps avoid direct window-level leakage, but all groups may share generator formulas, asset settings and waveform physics. A high anomaly score can reflect a load/RPM change, temperature drift, or simulation mismatch—not a bearing defect.
- The detector is multivariate *anomaly* detection, not supervised per-fault classification; it makes no independent claims that bearing wear, imbalance or misalignment can be distinguished reliably.
- No measurement calibration, actual defect-onset timestamp, probability of failure, industrial alarm safety, or RUL has been validated. A 99th-percentile training threshold is a toy baseline choice, not a field-tested alert rate.
- This version handles **only** MotorPulse synthetic events at 1024 Hz and 1024 samples/window, **not** the unknown native sampling rate and physical units of IMS records. IMS archival source and derivative rights remain **on hold**, as explained in [DATA_PROVENANCE.md](DATA_PROVENANCE.md).
- A source digest detects accidental file changes but is not a source-authenticity signature. Actual historical cross-version reproducibility requires future frozen-environment training/evaluation tooling (MP-033).

## Tests

```bash
python -m unittest discover -s tests -p 'test_anomaly.py' -v
python -m unittest discover -s tests -v
```

The regression suite creates reproducible synthetic exports in temporary directories, tests train-only access and deterministic replay, injects hostile split manifests and tampered files, checks finite-feature and sensor-null behavior, tests CLI no-overwrite semantics, and verifies that rule outputs and labels are never used as feature inputs.

See also [dataset cards](DATASET_CARDS.md), [simulation export](DATASET.md), [source-run split plans](SPLITS.md), and [scientific model assumptions](MODEL_ASSUMPTIONS.md).

**Next:** MP-011 held-out event/detection metrics; MP-033 experiment CLI/repeatability and MP-035 versioned model-artifact load/save.
