# MP-009 — Local IMS-style bearing record ingestion

**Scope:** dependency-free, bounded inspection of **user-provided local ASCII snapshot files**. No network access, no ZIP/RAR/7z extraction, no background downloads, no raw waveform redistribution, no trained AI, and no inferred defect onset or Remaining Useful Life (RUL).

The third-party bearing archive is **not** included in this repository. IMS original-provider attribution and unresolved distribution/derivative rights are recorded in [DATA_PROVENANCE.md](DATA_PROVENANCE.md) and the [IMS source card](sources/ims-bearings.source.json). Ingest only files lawfully obtained for your own use; do not commit IMS raw files, reconstructable signals, or derived summaries while redistribution permission remains unclear.

## How to use

After you have separately obtained the original data and **safely extracted** an archive into your own local `data/raw/` directory, locate a directory that directly contains timestamp-named ASCII records (no recursion). Example for an IMS **Test Set 2** layout:

```bash
python -m motorpulse.ims \
  --input-dir data/raw/ims/2nd_test/2nd_test \
  --test-set 2 \
  --sample-rate-hz 20000 \
  --expected-samples 20480 \
  --expected-channels 4 \
  --max-files 10 \
  --manifest data/external/ims-set2-local-report.json
```

The output parent `data/external/` must already exist. The manifest/report file **must not exist**; it is created exclusively and never overwritten. The importer prints counts but does not print or save raw waveforms.

An installed package also provides:

```bash
motorpulse-ims --help
```

**Important sampling note:** `20000`, `20480`, and `4` are *provisional user-supplied parameters*, commonly described in IMS-related literature, **not verified from an original archive in this project**. The importer deliberately has **no defaults** for sample rate, row count or channel count. Confirm these against your local IMS documentation, then supply the actual values. At a declared 20,000 Hz, 20,480 samples represent **1.024 seconds**, not precisely one second. Some secondary publications conflate 20,000 Hz, 20,480 samples and a one-second window; we do not silently resolve that discrepancy.

You can inspect the **100% handwritten synthetic parser fixture** without accessing any third-party data:

```bash
python -m motorpulse.ims \
  --input-dir tests/fixtures/ims_style_synthetic \
  --test-set 2 --sample-rate-hz 8 \
  --expected-samples 4 --expected-channels 4
```

This fixture intentionally has only four readings per channel. Its fake timestamp names and amplitudes are not NASA/IMS measurements, and 8 Hz has no relationship to the IMS acquisition rate.

## File and parse contract

The selected input directory must exist, be a real directory (not a symlink), and contain files named `YYYY.MM.DD.HH.MM.SS`, such as `2004.02.12.10.32.39`. Filenames must contain **real calendar dates**. Selected files are ordered chronologically by filename; `--max-files` selects the earliest N. Other files such as a README are skipped, and nested directories are not traversed. Timestamp-shaped symlinks and non-regular entries are rejected.

Each selected file must contain exactly `--expected-samples` lines of **whitespace-separated ASCII numerical values**, each with exactly `--expected-channels` columns. Both spaces and tabs are accepted; no header is assumed. These cases fail with explicit filename/line messages:

- Missing rows, extra rows, blank lines or the wrong number of columns.
- Invalid ASCII, headers, nonnumeric readings, NaN, Infinity, and squared-value arithmetic overflow.
- Invalid calendar filenames, symlinks or zero-byte records.
- Excessive bytes or line lengths, missing directories and invalid sampling parameters.

The scanner is **bounded**: 1–100 selected files per call, no more than 20,000 directory entries scanned, 16 MiB per selected file, 2,048 bytes per line, 1–32,768 rows and 1–16 columns. It processes one line at a time and retains **only statistics** for each channel, not the waveform. These are safety/resource limits for a local research utility, not standardized properties of the original experiment.

The importer **does not detect archives or inspect their embedded notices**. Do not point it at a ZIP; extracting untrusted archives separately requires traversal/bomb protections.

## Channel, time and label provenance

The local report contains the following:

| Field | Meaning |
|---|---|
| `source_card_id` | `nasa-pcoe-ims-bearings` (project reference card) |
| `test_set`, `run_id` | Explicit run grouping, e.g. `2` and `ims-set-2` |
| `filename`, `timestamp_local` | Strictly parsed file timestamp with **unknown timezone**, **not converted to UTC** |
| `channel_id`, `group_key` | Each channel number within its run (e.g. `ch-01`, `ims:set-2:ch-01`) |
| `bearing_id` | **null unless the user supplies an explicit mapping** with a source note |
| `rms_native`, `peak_to_peak_native` | RMS and peak-to-peak in the **declared native input unit** |
| `crest_factor` | `max(abs(value))/rms`, dimensionless |
| `sample_rate_hz_declared`, `snapshot_duration_s` | User-supplied rate and samples/rate |
| `value_unit_declared` | Defaults to `unknown`; no conversion or calibration is assumed |
| `sha256`, `bytes` | Hash and measured size of each locally read record |
| `original_archive_sha256`, `acquired_on` | **null unless measured/supplied by the user** |
| `ground_truth` | Per-window fault label, onset and RUL **all null** |

The data record is a **single acquisition**; it is not a single rotation, an asset independent of other channels, or a fault label. A local file's modification time is **not** used as the measurement time. IMS donors did not supply a verified timezone for the timestamps in this milestone, so no UTC offset or inferred elapsed-to-failure label is generated.

**Physical units:** Without original sensor calibration, it is unsafe to assume that sample numbers are `g`, `m/s²`, or volts. The default is `unknown`; a user may explicitly set `--value-unit g`, `m/s^2` or `V` only when verified. These data are **not** passed to MotorPulse AI's synthetic 1024-Hz FFT or rule-based health classifications.

## Optional explicit channel-to-bearing mapping

To preserve bearing grouping where the user has verified it locally, supply a small JSON mapping file:

```json
{
  "test_set": "2",
  "channels": {
    "1": "bearing-1",
    "2": "bearing-2",
    "3": "bearing-3",
    "4": "bearing-4"
  },
  "source_note": "Describe the locally inspected source and channel-map evidence"
}
```

Pass `--channel-map /path/to/your-map.json`. The mapping must cover every channel exactly, use positive bearing IDs and match the requested test set. Multiple channels **may map to the same bearing**. Mapping source notes are passed through as user assertions, *not verified by the importer*. The included fixture mapping is a hand-authored exercise, not proof of true IMS channels.

Without mapping, `bearing_id=null` is the **correct output**, rather than guessing a bearing from channel position. MP-028 will use the declared `run_id`, `group_key` and verified `bearing_id` to prevent leakage across related windows/channels.

## Optional acquisition evidence

Supply `--archive-sha256 <your-64-hex-checksum>` and `--acquired-on YYYY-MM-DD` **only if locally documented**. Their defaults are null; the importer does not fetch an archive, hash an unseen ZIP or invent a retrieval date. The actual text-record SHA-256 is computed locally.

`--manifest data/external/your-new-report.json` writes a single JSON report containing input directory, full file summaries, grouping and source metadata. Its content is locally derived from any inspected third-party files. **Do not add it to a public git repository** while source-data reuse rights remain unresolved. Use ignored `data/external/` or `data/processed/` paths and review `git status`.

## Testing / known gaps

```bash
python -m unittest discover -s tests -p 'test_ims.py' -v
python -m unittest discover -s tests -v
```

The tests use only [handwritten fixtures](../tests/fixtures/ims_style_synthetic/README.md), not IMS data. They verify sample RMS, timestamp parsing, chronological selection, nonfinite rejection, mapping validation, bounded file processing, subprocess CLI, report integrity and no-overwrite behavior.

**Not yet verified:** parsing a complete real IMS archive, original per-run channel map, sensor units, exact sampling clock, varying raw archive layouts, failure annotations, or derivative redistribution permission. The NASA catalog currently labels the source [`other-license-specified`](https://data.nasa.gov/dataset/ims-bearings). Public documentation describes three experimental test sets and often lists 20 kHz / 20,480 points, but this exact source pack has **not** been acquired or inspected here.

This milestone is an **adapter**, not an IMS benchmark, trained anomaly detector, RUL evaluator, or industrial condition-monitoring system.

### References

- [NASA PCoE bearings repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) — original distribution/citation; credits IMS University of Cincinnati and Rexnord Technical Services.
- [NASA IMS Open Data entry](https://data.nasa.gov/dataset/ims-bearings) — distribution and license metadata.
- [Open-access peer-reviewed IMS dataset description](https://pmc.ncbi.nlm.nih.gov/articles/PMC9503590/) — literature-level record layout, channel counts and reported nominal sampling; **not a substitute for locally inspected archive documentation**.
