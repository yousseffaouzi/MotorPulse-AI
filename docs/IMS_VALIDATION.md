# MP-028 — Local IMS report validation and leakage-safe preprocessing

**Scope:** offline, user-supplied IMS-style research files. No dataset is bundled, downloaded or uploaded, and no trained fault model, calibrated bearing diagnosis, fault-onset time or Remaining Useful Life (RUL) is inferred. The IMS source card and [DATA_PROVENANCE.md](DATA_PROVENANCE.md) still mark **raw/derived redistribution permission unresolved**.

The validation and feature tools are independent of MotorPulse AI's **synthetic 1024 Hz plant**. They require your locally documented sample rate and native physical unit. Do not treat a native voltage signal as acceleration in g without a verified sensor calibration.

## 1. Validate a locally inspected report

First create an inspection report from your own records with the MP-009 adapter. The 100% handwritten parser fixtures can be used instead:

```bash
python -m motorpulse.ims \
  --input-dir tests/fixtures/ims_style_synthetic \
  --test-set 2 --sample-rate-hz 8 \
  --expected-samples 4 --expected-channels 4 \
  --manifest /tmp/ims-inspection.json

python -m motorpulse.ims_validation \
  --report /tmp/ims-inspection.json --verify-files \
  --expected-interval-s 10 \
  --out /tmp/ims-quality.json
```

Both output report paths must be new files in existing local directories; reports are not committed. The installed command is `motorpulse-ims-validate`. The validation report preserves `source_card_id`, `run_id`, declared units, number of channels, nominal Nyquist frequency (`fs/2`) and DFT bin spacing (`fs/N`). Sample-count and sample-rate consistency are checked, but this **does not verify upstream sensor calibration or clock accuracy**.

**Checks:**

- Every record is from the declared test set/run and has a strict, calendar-valid timestamped filename. Duplicate records and non-increasing time are rejected.
- Filename timestamps are **naive local times**, without a verified UTC offset. They are not interpreted as UTC. Optional `--expected-interval-s` issues a `cadence_deviation` warning for gaps over a ±5% or 1 ms tolerance (whichever is larger); overlapping nominal acquisition windows receive `window_overlap`.
- The expected channel count and 1-based ordering must match every record. Each channel has a stable `ims:set-X:ch-YY` group key. Physical bearing identity remains `null` unless a separately documented channel mapping was provided at ingestion.
- Measurement summary fields must be finite and physically coherent: RMS, peak-to-peak, crest nonnegative; crest ≥1 when RMS is positive; zero RMS cannot coexist with nonzero peak-to-peak or crest.
- Native units are kept **exactly** as declared: `unknown`, `g`, `m/s²` or `V`. There is no automatic conversion. `unit_unverified` and `bearing_mapping_unverified` are information flags; `flatline_review` and `high_crest_review` (default crest ≥6) are **review flags, not machine-fault diagnoses**.
- `--verify-files` recomputes SHA-256 and exact bytes from each selected original local file. It detects changed/missing data compared with the MP-009 inspection report. When disabled, hashes are only validated as formatted metadata and must **not** be represented as re-verified.
- Report-size, selected-file, issue-count, and file-byte limits are enforced. Structural inconsistency and fabricated window-level failure truth cause validation errors.

### Interpretation

Flatline signals can reflect constant sensor offsets, unused inputs or faults; the importer **does not decide which**. High crest values can arise from impact, noise or instrumentation; the code does not label them as bearing defects. Frequency resolution and Nyquist are *declared sampling geometry*, not proof an acquisition is anti-aliased.

## 2. Optional native-rate Hann single-bin amplitude

For a **locally obtained** timestamp-named ASCII record, the public Python function measures one explicitly requested tone frequency at the nearest DFT bin. It uses a periodic Hann window, per-channel mean subtraction, and original sampling rate without any resampling:

```python
from pathlib import Path
from motorpulse.ims_tone import native_hann_tone

result = native_hann_tone(
    Path("tests/fixtures/ims_style_synthetic/2004.02.12.10.32.39"),
    sample_rate_hz=8, expected_samples=4, expected_channels=4,
    requested_hz=2, value_unit="unknown",
)
print(result["analyzed_frequency_hz"], result["amplitudes"])
```

This fixture has `N=4`, `fs=8 Hz`, hence `Δf=2 Hz`, `f_Nyquist=4 Hz`. Target must lie strictly between DC and Nyquist and resolve to an interior bin. `requested_frequency_hz` and `analyzed_frequency_hz` are distinguished explicitly. The estimator computes:

```text
w[n]   = 0.5 - 0.5 cos(2π n / N)    (periodic Hann)
k      = round(f_requested / (fs/N)), 1 <= k < N/2
μ      = (1/N) sum_n x[n]
X[k]   = sum_n (x[n] - μ) w[n] exp(-j 2π k n / N)
A_peak = 2 |X[k]| / sum_n w[n]
```

All amplitude output remains in the **declared input unit**, and is a **peak estimate** rather than RMS. An off-bin sinusoid may be underestimated due to Hann scalloping/leakage. No resampling is done, so no *new digital decimation aliasing* is introduced—but any aliasing in the original acquisition is **unknown**. The estimator cannot establish mechanical frequencies (BPFO/BPFI/etc.) without actual bearing geometry, rotational speed and calibration; it does not identify a fault by itself.

This is an optional single-bin feature, **not a full FFT, PSD, bearing-envelope spectrum, or anti-alias filter**. No measurement is converted from volts to g. Relevant methodology: [NIST spectral windowing and leakage](https://tf.nist.gov/phase/Properties/ten.htm).

## 3. Train-only scaling and leakage protection

`fit_train_scaler` works on whole, explicitly separated *run reports*, and fits three descriptive time-domain features (`rms_native`, `peak_to_peak_native`, `crest_factor`) using **training runs only**. A held-out run must be present and disjoint; no report may appear in both partitions. The scaler rejects mixing units, sample rates or window sizes and refuses the `unknown` unit for cross-run fitting.

```python
from motorpulse.ims_validation import fit_train_scaler, transform_report

# train_report and test_report are separate locally inspected runs:
scaler = fit_train_scaler([train_report], [test_report])
training_features = transform_report(train_report, scaler, partition="train")
heldout_features = transform_report(test_report, scaler, partition="heldout")
```

Each feature is transformed using the *population* mean and standard deviation **of training records only**: `z = (value - mean_train) / sd_train`. If the training feature is constant (`sd_train = 0`), transformed values are set to **0** and `constant=true` is recorded; no arbitrary test-data variance is fitted.

These APIs preserve `run_id`, `group_key`, `bearing_id`, source-record SHA-256 and timestamp metadata in resulting **in-memory** feature records. They never impute or guess fault labels. Save **no IMS-derived transformations to a public GitHub tree** before obtaining permission.

**Leakage guard:** The entire source run (including related channels and neighboring acquisitions) must reside in one partition. MP-030 now [plans whole-run train/validation/test holdouts](SPLITS.md), treating each IMS test set as a conservative independent run boundary; no splitting related bearings/channels inside a test set. Do not normalize the entire dataset *before* splitting. See [scikit-learn's data-leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) for the methodological rationale; this project does not require scikit-learn at runtime.

## Exploratory local quality reports

MP-029 adds [EDA.md](EDA.md) and `motorpulse-eda --source ims --input YOUR_INSPECTION.json --out NEW_LOCAL_REPORT.json --verify-files`. It summarizes per-channel native-unit distributions, first/last timestamp trends and MP-028 inspection flags, preserving **unknown timezone**, **null failure labels**, and **local-only redistribution hold**.

## 4. Explicit limitations / follow-up

- This implementation has been checked on **handwritten synthetic input fixtures only**. Original IMS ZIP layouts, sampling rate, channel/bearing mapping, units, timezone and failure annotations remain unverified.
- No resampling, anti-alias filtering, vibration velocity conversion, missing-data imputation, test-label inference or model evaluation is performed. Native-rate tone amplitude is optional and cannot establish real motor-fault classes.
- A report is at most **100 selected snapshots**, with limits inherited from MP-009. The local quality report is not a scalable full-run database; batch comparison and performance benchmarking follow.
- `run_id=ims-set-N` is a conservative test-set grouping placeholder, **not** an independently verified rig/bearing ID; user-provided mapping source notes remain external assertions.
- Quality warnings do not establish a sensor failure and cannot substitute for hardware verification.
- This local validation step does **not** clear IMS-data rehosting or derived-feature publication rights, which remain on hold under [DATA_PROVENANCE.md](DATA_PROVENANCE.md).

## Test commands

```bash
python -m unittest discover -s tests -p 'test_ims_validation.py' -v
python -m unittest discover -s tests -p 'test_ims_tone.py' -v
python -m unittest discover -s tests -v
```

Both test modules use only small hand-authored ASCII fixtures and temporary files. They never download, embed or regenerate excerpts of IMS data.
