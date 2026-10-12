# MP-030 — Leakage-resistant train/validation/test split plans

**Purpose:** generate deterministic, reviewable **split plans** before selecting features, fitting preprocessing, training an anomaly detector or measuring held-out performance. The code does **not** train, evaluate, move or republish data. It requires Python 3.11+ and uses the standard library only.

MotorPulse-AI has two distinct data sources:

- **Synthetic**: our generated motor events have controlled scenario *ground truth*, but uncalibrated rule-based health states are not proven failure outcomes.
- **IMS**: local user-supplied real bearing experiment summaries. The true fault-onset time, per-window label, instrument timezone and physical bearing-to-channel mapping remain unverified. Redistribution of original *and derived* IMS data is still **on hold** under [DATA_PROVENANCE.md](DATA_PROVENANCE.md).

## A. Independent, complete-run holdout (recommended)

One source manifest/report is one complete **run group**. All its motor assets, channels, dates and windows belong to **one** partition. Three partitions (train, validation, test) are created only when at least **three independent groups** are provided. Assignment is deterministic using a caller-supplied split seed and the source run's stable identity; **fault labels and health output never control assignment**.

Example with separate simulator seeds (each output directory must be new):

```bash
mkdir -p datasets
python -m motorpulse.export --out-dir datasets/seed11 --seed 11 --ticks 30 --format jsonl
python -m motorpulse.export --out-dir datasets/seed22 --seed 22 --ticks 30 --format jsonl
python -m motorpulse.export --out-dir datasets/seed33 --seed 33 --ticks 30 --format jsonl

python -m motorpulse.splits --source synthetic \
  --input datasets/seed11/manifest.json \
          datasets/seed22/manifest.json \
          datasets/seed33/manifest.json \
  --seed 42 --out datasets/group-split.json
```

The installed command is `motorpulse-split`. The CLI supports `--train-ratio 0.6 --validation-ratio 0.2 --test-ratio 0.2`; all ratios must be **positive, finite and sum to 1**. Since whole runs are indivisible, the requested fractions are **targets by run-group count, not exact row percentages**. The planner reserves at least one complete group for each partition; with three groups the result necessarily has 1/1/1 groups, regardless of nominal ratios. In larger sets it assigns remaining groups to the largest unmet target count. Imbalanced sizes and fault types are reported as evaluation-design concerns, **not fixed by leaking source labels into split assignment**.

To generate an IMS plan, use **at least three distinct, locally inspected** IMS runs (e.g. one report per test set) with source verification:

```bash
python -m motorpulse.splits --source ims \
  --input data/external/ims-test1-inspection.json \
          data/external/ims-test2-inspection.json \
          data/external/ims-test3-inspection.json \
  --out data/reports/ims-group-split.json
```

The importer from [IMS_INGESTION.md](IMS_INGESTION.md) creates these local report files. The splitter checks their structural quality using [IMS_VALIDATION.md](IMS_VALIDATION.md). It **never downloads the IMS archive**. A test-set is conservatively treated as **one rig/run**, with all associated bearings, channels and acquisition times together. Splitting different channels or bearings *within* a shared run is **not enabled**, even if labels appear to differ.

**Important:**
- A duplicate `run_id` or synthetic generator-run fingerprint is rejected, including synthetic exports with the same seed/configuration/start but different tick counts.
- Cross-IMS-run **identical raw-record SHA-256 values** are rejected, to prevent exact duplicated recordings across partitions. The splitter does not re-read raw IMS waveforms; these hashes are verified *as metadata*. Re-validate the inspection files with `motorpulse-ims-validate --verify-files` if your local original files are still available.
- Synthetic inputs are validated by the existing EDA reader, which recomputes SHA-256 and byte sizes of their JSONL/CSV data files. CSV-only export is unsupported because its missing-value and nested-field parsing is lossy.
- The group plan embeds **source data identities and digests**, not absolute source file paths, raw sensor samples, or validation/test failure labels. It does not imply independence between distinct synthetic seeds with identical programmed scenarios or between shared physical rigs documented as different test sets.

## B. Explicit synthetic chronological holdout (exploratory only)

A *single* synthetic run can be partitioned in time, with **all assets at a given tick staying together**. This is not an independent-run or independent-machine experiment: waveform generation conditions and scripted fault profiles remain related between partitions. Use it as a secondary diagnostic experiment, **not** as the main generalization estimate.

```bash
python -m motorpulse.export --out-dir datasets/time-run --ticks 40 --format jsonl --seed 42

python -m motorpulse.splits --source synthetic \
  --input datasets/time-run/manifest.json \
  --chronological --purge-ticks 4 \
  --out datasets/chronological-split.json
```

The plan includes inclusive train/validation/test **tick ranges** and two explicit **discarded purge ranges** between partitions. It never shuffles timestamps. The minimum discarded gap is

`max(4, ceil(window_duration_seconds / virtual_step_seconds))` ticks.

The first term prevents a five-tick rolling RMS from pulling earlier partition values into the next partition; the second accounts for nominally overlapping synthetic sample windows if simulation ticks are faster than their waveform duration. The default 1.5-s step and 1-s waveform permit **4 purge ticks**. A 0.1-s step and 1-s waveform require at least **10 purge ticks**. Small runs that cannot fit three nonempty ranges *after* two purges are rejected.

The purge gap is a defense for these explicitly modeled window dependencies, **not proof of statistical independence**. Multi-asset labels and scripted scenarios still correlate across the run. **IMS chronological splitting is intentionally prohibited**: without independent rig, bearing and channel grouping evidence, that shortcut would overstate real-world transfer performance.

[MP-032 dataset cards](DATASET_CARDS.md) carry source, label and licensing disclosures and can bind to local source provenance. Split plans govern assignment and leakage; they do **not** replace dataset cards or grant data-distribution rights.

## Plan format and validity

All JSON plans include:
- `split_version`, `policy`, `source_type`, `plan_sha256`, and explicit source identities/provenance.
- `partitions.train`, `partitions.validation`, `partitions.test`. Grouped plans store exact `group_ids`, `source_ids`, and per-partition record counts. Chronological plans instead store tick ranges, record counts and `purged_ranges`.
- `preprocessing_rule`: fit **scalers, imputers, feature selection and thresholds on training only**. The actual MP-028 scaler will refuse overlapping runs, mixed physical units, unverified units or inconsistent sample rates.
- `label_blind_assignment=true`. No held-out source truth is used to decide the split. Synthetic programmed scenarios must not be mistaken for model predictions; IMS fault-onset/RUL remain unknown.
- No wall-clock creation timestamp or absolute filesystem location, so the **same verified data and input choices produce byte-stable split plans**.

The splitter is limited to **3–100 complete source runs** for grouped mode and reuses the earlier dataset/inspection bounds. It fails on duplicates, missing or corrupted inputs, invalid ratios/seeds, exhausted holdout groups and invalid purge gaps. Outputs use exclusive-create semantics: **existing plans are never overwritten**.

### Security / reproducibility notes

A source SHA-256 verifies **file identity**, not a dataset's scientific truth, licensing, original calibration or independence of two experiments. A split manifest is an *assignment plan*, not automatic protection for arbitrary downstream scripts. MP-011 uses the same [whole-run plans for held-out synthetic model-vs-rule evaluation](EVALUATION.md), with no validation/test refitting or label-driven threshold. MP-010 now implements an [ML baseline](ANOMALY_BASELINE.md) that **actively validates the full MP-030 plan**, source-group identities and digests and consumes training groups only when fitting scaler and threshold. Future experiments should use the plan as an authoritative input and assert source/tick membership before fitting anything. No high-level evaluation metrics, class balance guarantees, confidence intervals or failure probabilities are claimed.

The project never commits raw or derived IMS experiments, source-specific quality summaries or split plans containing IMS data while redistribution rights are unresolved. Store them in ignored local `data/reports/` or `data/external/`.

### Testing

```bash
python -m unittest discover -s tests -p 'test_splits.py' -v
python -m unittest discover -s tests -v
```

All tests create temporary, entirely synthetic MotorPulse exports or handcrafted IMS-style examples. No real bearing archive or external download is used.

Methodological background: [scikit-learn model selection — grouped cross validation](https://scikit-learn.org/stable/modules/cross_validation.html), [time-series split and gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), and [data leakage prevention](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage). Scikit-learn is **not required** to use this splitter.
