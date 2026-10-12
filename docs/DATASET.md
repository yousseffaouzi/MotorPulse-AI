# MP-008 — Reproducible synthetic dataset export

MotorPulse AI exports **SIMULATED** motor-condition feature events. These records contain known, scripted fault labels; they are **not measured industrial telemetry**, validated health assessments, failure probabilities, or remaining-useful-life predictions. Read [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md) before using the files for experiments.

## Quick start

From the project root on Python 3.11+ (standard library only):

```bash
python -m motorpulse.export --out-dir datasets/demo-001 --ticks 12 --format both \
  --config docs/examples/operations-v1.json --seed 42 \
  --start-time-utc 2026-01-01T00:00:00Z --step-seconds 1.5
```

**The parent directory must already exist**. For example, run `mkdir -p datasets` on Linux/macOS first, or `mkdir datasets` in PowerShell. The command creates `datasets/demo-001` and fails if it already exists. No files are overwritten; there is deliberately no `--force`. All paths are local. The installed CLI command is `motorpulse-export` with the same arguments:

```bash
motorpulse-export --out-dir datasets/healthy-baseline --ticks 100 --format jsonl --seed 42
```

`--format csv`, `--format jsonl` and `--format both` are supported (default `both`). Defaults for omitted simulation settings match `python -m motorpulse`, and `--config` accepts the same bounded, validated UTF-8 JSON used by the server. Start with the default 3 assets or supply 1–12 motors. Export limits: **1–1000 ticks**, **64 MiB per data file**, and an existing output parent. Each completed export has 1 to 12,000 event rows. The target must be a new directory; an existing file, directory or symlink is rejected. An export error removes only its newly created output directory, rather than leaving a partial dataset.

### Output layout

```text
datasets/demo-001/
  events.csv         # present for csv/both, one motor event per row
  events.jsonl       # present for jsonl/both, one JSON object per line
  manifest.json      # always present
```

**JSONL** uses UTF-8, one valid JSON object per line and `\\n` line endings; nested objects/lists and missing vibration values remain native JSON. **CSV** uses UTF-8, a fixed ordered header and `\\n` line endings. In CSV, nested fields are compact JSON strings, missing measurements are empty cells, and numbers are text representations that a reader should parse according to the data dictionary. A motor *name* starting with a spreadsheet formula marker (`=`, `+`, `-`, `@`, after leading whitespace) receives a leading apostrophe **only in CSV**; JSONL retains the original name. Do not assume CSV blanks and names are byte-for-byte reversible to their JSONL types; CSV is the convenient tabular interchange format, JSONL is the loss-preserving reference.

## Schema and data dictionary

Both formats contain the same logical **per-asset feature events**. They do **not** contain the 1024 raw waveform samples. Every event has:

| Field(s) | Unit / meaning |
|---|---|
| `export_id` | Repeatable content-identity prefix, not a global run identifier |
| `schema_version`, `source` | Telemetry `1.0.0`, `synthetic` |
| `tick`, `recorded_at_utc`, `timestamp_utc` | Virtual tick (starting at 1), UTC snapshot / event start time |
| `event_id`, `asset_id`, `name` | Simulated event and motor identity / display label |
| `scenario`, `severity` | **Effective synthetic motor-fault ground truth**, strength 0–1; not a diagnosed defect |
| `configured_scenario`, `configured_severity`, `onset_tick`, `duration_ticks` | Programmed synthetic scenario truth / boundaries |
| `progression`, `start_severity`, `ramp_ticks`, `ramp_fraction`, `fault_phase` | Constant/linear/exponential schedule, numeric ramp position and phase; **not** a failure probability |
| `sensor_quality`, `sensor_quality_reasons` | Injected `good`, `missing`, `outlier` quality label and explanations |
| `health`, `reasons` | Uncalibrated demo threshold output, or `unavailable` / `suspect` with reasons |
| `rpm`, `shaft_frequency_hz` | RPM and nominal shaft fundamental in Hz |
| `temperature_c`, `load_factor` | °C and dimensionless synthetic load multiplier |
| `sample_rate_hz`, `sample_count`, `window_duration_s` | Hz, samples and seconds (defaults 1024 Hz × 1024 = 1 s) |
| `units` | Unit metadata object, e.g. acceleration `g` rather than velocity |
| `rms_g`, `peak_to_peak_g`, `crest_factor` | Acceleration RMS (g), peak-to-peak (g), dimensionless crest |
| `spectral_window`, `spectral_bin_hz`, `dominant_frequency_hz` | Hann window label, bin spacing (Hz), dominant frequency (Hz) |
| `shaft_1x_amplitude_g`, `shaft_2x_amplitude_g` | Hann-windowed harmonic acceleration estimates (g **peak**) |
| `band_80_400_rms_g` | Synthetic acceleration band RMS (g RMS), inclusive of 80–400 Hz |
| `rolling_window_ticks`, `rolling_observations`, `rolling_valid_observations` | Five-tick window capacity and sample counts (vibration missingness tracked) |
| `rolling_rms_mean_g`, `rolling_temperature_mean_c` | Mean of recent valid per-window RMS (g) and temperature (°C) |
| `sensor_drift_g`, `operating_config` | Synthetic DC acceleration offset and scheduled operating settings |

Missing sensor readings are **JSON null** in affected vibration fields and **empty CSV cells**, never numerical zero. `health="unavailable"` means machine classification was suppressed because vibration is missing; `health="suspect"` means the simulator injected an outlier. The configured fault may still be active. `rolling_valid_observations` is the number of nonmissing vibration records, while `rolling_observations` includes missing ticks; never conflate the two.

The fixed ordered **CSV columns** and allowed JSONL keys are defined by `motorpulse.export.EXPORT_FIELDS`; JSONL serialization sorts object keys alphabetically and JSON object key order has no semantic meaning. An unexpected changed telemetry field causes export failure rather than silently dropping information. The native snapshot schema and cross-field constraints are documented in [TELEMETRY.md](TELEMETRY.md) and [snapshot.schema.json](snapshot.schema.json).

## Manifest / provenance

`manifest.json` includes:

- `dataset_type`, `synthetic_only`, `manifest_version` and source telemetry `schema_version`
- `export_id`: first 24 hex digits of a SHA-256 over canonical **configuration hash + source-code hash + seed + virtual start time + step + number of ticks + schema version**. Deterministic for identical inputs and source files, **not** a globally unique identifier. Deliberate repeat exports reuse it.
- `config_sha256` (SHA-256 over sorted/minified canonical JSON with fully expanded scenario defaults) and the full `configuration`
- `model_source_sha256` (SHA-256 over the filenames and raw bytes of seven source modules used in generation), `source_filenames`, and the packaging `package_version`. A package-version string alone does not identify a working-tree revision.
- `seed`, `ticks`, `events`, `assets`, `sample_rate_hz`, `sample_count`, `virtual_start_utc`, `virtual_end_utc`, and `step_seconds`.
- `created_at_utc`: **real UTC export-creation time**, deliberately *separate* from simulated measurement times. This field may differ on an identical replay.
- `format`, `columns`, `files`: exact byte sizes and SHA-256 of each data file, and explicit descriptions of label semantics.

**Reproducibility contract:** For identical inputs, source files and Python execution environment, data file contents, event ordering, data checksums and export IDs are deterministic. The manifest's `created_at_utc` is wall-clock metadata and is *not* expected to be byte-identical across runs. A different Python version/platform may change floating-point formatting or PRNG behavior; cross-platform byte-level identity has not been certified. Dataset exports are not cryptographically signed, and a hash alone does not establish the truth of the data.

`event_id` from the simulator can repeat across two separate exports with identical seed/ticks. Use `export_id + event_id` as an **experiment-scoped** join key, not a globally unique production run key.

## Python round-trip / checksum examples

```python
from pathlib import Path
import csv, hashlib, json

folder = Path("datasets/demo-001")
manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
for filename, meta in manifest["files"].items():
    raw = (folder / filename).read_bytes()
    assert len(raw) == meta["bytes"]
    assert hashlib.sha256(raw).hexdigest() == meta["sha256"]

with (folder / "events.jsonl").open(encoding="utf-8") as stream:
    events = [json.loads(line) for line in stream]
assert len(events) == manifest["events"]
with (folder / "events.csv").open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream))
assert len(rows) == len(events)
print(manifest["export_id"], "verified")
```

The offline [exploratory quality reporter](EDA.md) can produce per-motor feature distributions, missingness counts, rule/label-category counts and trend samples from this export's validated JSONL file. Run `python -m motorpulse.eda --source synthetic --input YOUR_EXPORT_DIR --out NEW_REPORT.json`. It does not train an ML model.

All events are **labelled synthetic examples**, so ML users must split by run/asset appropriately, separate fault truth from model output, and avoid training/evaluating on trivially duplicated seeds or time-adjacent windows. This exporter does *not* establish external dataset licenses, validate hardware faults, train models, or prevent downstream data leakage by itself. For a separate, **real** experimental IMS bearing dataset and unresolved third-party rights, see [DATA_PROVENANCE.md](DATA_PROVENANCE.md) and [sources/ims-bearings.source.json](sources/ims-bearings.source.json). Do not label synthetic exports as IMS measurements. The [IMS_INGESTION.md](IMS_INGESTION.md) adapter is a separate, local-only ingestion workflow; it neither modifies synthetic telemetry nor makes license or failure-label claims.

## Local verification

```bash
python -m unittest discover -s tests -p 'test_export.py' -v
python -m unittest discover -s tests -v
```

For provenance, intended use and licensing distinctions, see the [versioned synthetic dataset card](../motorpulse/cards/synthetic-v1.json) and [MP-032 run-card generator](DATASET_CARDS.md). A generated run card includes verified export file, configuration and model-source SHA-256 digests. The software's MIT license is **not** claimed as an independently granted license for every generated dataset.

The exporter uses only the Python standard library's `csv`, `json`, `hashlib` and filesystem tools. CSV empty-cell semantics follow [Python's CSV module documentation](https://docs.python.org/3/library/csv.html); JSONL uses the [JSON Lines UTF-8/newline conventions](https://jsonlines.org/).
