# MP-029 — Reproducible exploratory data-quality reports

**Status:** dependency-free, local-first *descriptive* reporting for (a) MotorPulse AI's reproducible **synthetic** event exports and (b) already-inspected **user-supplied local IMS-style** bearing records.

The output is **not** a trained anomaly detector, real-world failure predictor, RUL estimate or diagnostic certification. For external IMS materials, reuse and derived-data redistribution rights remain unresolved: **do not commit real IMS-derived reports**. See [DATA_PROVENANCE.md](DATA_PROVENANCE.md).

## 1. Reproducible synthetic example

From the repository root on Python 3.11+, using only the standard library:

```bash
mkdir -p datasets
python -m motorpulse.export --out-dir datasets/demo-eda --ticks 20 --format both \
  --config docs/examples/operations-v1.json --seed 42

python -m motorpulse.eda --source synthetic --input datasets/demo-eda \
  --out datasets/demo-eda/quality.json --format json

python -m motorpulse.eda --source synthetic --input datasets/demo-eda \
  --out datasets/demo-eda/quality.md --format markdown
```

Alternatively, use the installed `motorpulse-eda` script. All report paths must be **new files in existing directories**. Neither export nor reporting overwrites an existing result.

The synthetic reader **requires `events.jsonl`** (`--format jsonl` or `both`). A CSV-only export is deliberately rejected: JSONL preserves types, nested values and JSON `null` unambiguously, while CSV blanks and names may be lossy. When CSV is also present, its file size and SHA-256 are checked against the manifest, but event aggregates come from JSONL.

The reader verifies the source manifest, hashes and exact sizes of data files; validates record provenance, chronological ticks, distinct motor events and expected cardinalities. It rejects corrupted data, NaN/nonfinite feature values, unsafe input paths, and inconsistent sensor-quality/health states. Hard bounds are **12,000 events**, **64 MiB per source data file** and **16 KiB per JSONL line**. Reports are in-memory summaries, not a raw waveform dump.

Synthetic output contains per-asset:

- Counts for programmed `scenario` **ground truth**, injected `sensor_quality`, and uncalibrated rule-based `health`, as distinct categories.
- For vibration RMS, temperature, RPM, crest and 80–400 Hz band RMS: number observed, number missing, min, P05, median, mean, P95, max and population standard deviation. Percentiles use sorted observations with linear interpolation between ranks, and **null values are excluded rather than converted to zeros**. An entirely missing feature receives null summary statistics.
- First/last **six** tick samples of vibration RMS and temperature. For short runs, all values are included; these are **not an exhaustive chart**.
- Reproducibility metadata (`export_id`, config/source-code digests, virtual UTC time, sample rate/count and dataset file digest). The source manifest's wall-clock creation timestamp is intentionally omitted from EDA output; identical export data with identical source generation code yield equal EDA bytes even when regenerated into another directory.

The Markdown representation provides human-readable tables and compact numeric trend samples. The JSON representation remains the machine-readable reference, with all numeric values and explicit null semantics retained.

## 2. Local IMS report example (handwritten fixture only)

```bash
python -m motorpulse.ims \
  --input-dir tests/fixtures/ims_style_synthetic \
  --test-set 2 --sample-rate-hz 8 --expected-samples 4 \
  --expected-channels 4 --manifest /tmp/ims-eda-inspection.json

python -m motorpulse.eda --source ims \
  --input /tmp/ims-eda-inspection.json \
  --verify-files --expected-interval-s 10 \
  --out /tmp/ims-eda-quality.json --format json
```

You may also select `--format markdown`. The **test fixtures are handwritten numbers and not IMS recordings**. For real user-supplied data, use only your locally held records and store all generated results in ignored `data/external/`, `data/reports/`, or another untracked local path.

IMS mode reuses the strict MP-028 local report validator. It checks sample/channel/run consistency and timestamp chronology, and optionally recomputes source-file SHA-256 when `--verify-files` is supplied. Without that flag, any inspection-record SHA-256 is **metadata not independently rechecked at reporting time**.

Per-channel summary fields include native RMS, peak-to-peak and crest distributions, native unit as declared, documented bearing mapping or `null`, and first/last acquisition timestamps. The report carries forward the MP-028 review-only flag counts: `flatline_review`, `high_crest_review`, `unit_unverified`, `bearing_mapping_unverified`, `cadence_deviation` and `window_overlap`, as applicable.

Crucially, original filename timestamps have **unknown timezone**, are never converted to UTC, and **per-window fault labels, fault onset and RUL remain null**. A high-crest sample is an inspection flag, not a verified bearing failure. Native voltages are **not converted to g** and the synthetic demo rules are **never applied** to IMS data.

MP-032 adds [dataset cards](DATASET_CARDS.md) documenting provenance, true/unknown labels and reuse rights. Exploratory summaries complement these disclosures but are not a source-license clearance or dataset card.

## 3. JSON shape

Both output types use `report_version="1.0.0"` and identify `source_type` and `publication_status`.

| Synthetic reports | Local IMS reports |
|---|---|
| `export_id` and synthetic source/config file hashes | `source_card_id`, `run_id`, `test_set` |
| `per_asset.{asset_id}.features` | `per_channel.{group_key}.features` |
| `synthetic_fault_truth_counts`, `sensor_quality_counts`, `heuristic_health_counts` | `verification.issues_by_code` and whether file checksums were rechecked |
| `trend_sample_first_last` with virtual `timestamp_utc` | `trend_sample_first_last` with naive `timestamp_local` |
| `synthetic_only=true`, `publication_status=synthetic_demo` | `synthetic_only=false`, `publication_status=local_only_do_not_redistribute` |
| Scripted fault truth is defined by our simulation | `ground_truth.window_fault_label`, `fault_onset_time`, `rul_seconds` are **null** |

**Do not combine** these two report types and infer that synthetic motor-fault labels represent ground truth for experimental bearings. In particular, simple counts of rule-based `health="critical"` are not predictive-maintenance model performance metrics.

## 4. Validation, security and limitations

```bash
python -m unittest discover -s tests -p 'test_eda.py' -v
python -m unittest discover -s tests -v
```

The exporter is bounded and streaming at input, but descriptive distributions store at most 12,000 values per feature in memory. This is sufficient for the initial software lab, **not a full-run big-data processing engine**. Grouped trend samples contain at most 12 first/last observations per asset/channel.

The tools make **no network calls** and write report files with exclusive-create semantics. They do not require NumPy, Pandas, scikit-learn or plotting libraries. Input should still be trusted local experimental material: validation and hashing do not establish licensing, truth of upstream metadata, verified hardware calibration, or industrial safety.

For later leakage-safe learning, reports are **exploration only**. MP-030 now implements [deterministic split plans](SPLITS.md): keep entire source runs in one partition by default, or explicitly choose **synthetic-only** purged chronology for exploratory analysis. Downstream fitted models must consume the plan and fit transforms using training partitions only. Fit preprocessing on training groups only; adjacent per-window random splits and feature normalization over held-out runs are unsafe.

Further context: [IMS_VALIDATION.md](IMS_VALIDATION.md), [IMS_INGESTION.md](IMS_INGESTION.md), [DATASET.md](DATASET.md), and [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md).
