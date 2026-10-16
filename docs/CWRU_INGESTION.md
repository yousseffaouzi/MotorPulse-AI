# MP-031 — Local-only CWRU seeded-fault adapter

MotorPulse AI can inspect **user-supplied local** Case Western Reserve University (CWRU) Bearing Data Center MATLAB-v5 files without downloading or republishing the source measurements. This adapter is intentionally conservative: it supports one explicitly named real-double vector at a time, emits summary/provenance only, and requires a separate metadata JSON instead of inferring test conditions from a filename.

This is **not** a run-to-failure or remaining-useful-life (RUL) dataset adapter. The official Bearing Data Center pages describe normal data and single-point bearing faults seeded using **EDM**. Those seeded conditions can support local condition-classification research, but they are not observed degradation trajectories, failure times or physical RUL labels.

## Official sources and project rights policy

Use the original provider pages rather than third-party mirrors:

- Bearing Data Center: `https://engineering.case.edu/bearingdatacenter`
- Data download/index page: `https://engineering.case.edu/bearingdatacenter/download-data-file`

The official pages reviewed for MP-031 describe the bearing test apparatus, normal/fault data, single-point EDM defects, documented 0–3 hp load conditions, fault diameters, and 12 kHz / 48 kHz acquisition groups. They also provide MATLAB downloads. This project review did **not** establish an explicit dataset-specific redistribution license on those official pages.

MotorPulse AI therefore records CWRU redistribution status as **unverified_for_redistribution**. Public download availability is not treated as permission for this repository to rehost original files or publish derived measurement tables. Keep source files and any measurement-derived outputs local until a documented rights review establishes what redistribution is permitted. This is a conservative project policy, not a legal ruling.

The machine-readable review is [sources/cwru-bearings.source.json](sources/cwru-bearings.source.json). No CWRU measurement file, sample vector or derived feature table is bundled with the repository or test suite.

## Why metadata is explicit

Do **not** guess fault type, bearing location, fault diameter, load, sampling rate or MATLAB variable from a numeric filename. Before inspection, create a small local metadata JSON from the official page corresponding to the file you obtained.

Example for a drive-end, 7-mil inner-race seeded fault at 1 hp and 12 kHz:

```json
{
  "metadata_version": "1.0.0",
  "source_url": "https://engineering.case.edu/bearingdatacenter",
  "file_name": "105.mat",
  "channel_variable": "X105_DE_time",
  "bearing_location": "drive_end",
  "fault_type": "inner_race",
  "fault_diameter_mils": 7,
  "outer_race_position": null,
  "load_hp": 1,
  "sample_rate_hz": 12000,
  "value_unit": "unknown"
}
```

Supported local metadata values are deliberately narrow:

| Field | Accepted value |
|---|---|
| `bearing_location` | `drive_end` or `fan_end` |
| `fault_type` | `normal`, `inner_race`, `ball`, `outer_race` |
| `fault_diameter_mils` | null for `normal`; otherwise 7, 14, 21, 28 or 40 |
| `outer_race_position` | required only for outer-race faults: `3_oclock`, `6_oclock`, `12_oclock` |
| `load_hp` | integer 0, 1, 2 or 3 |
| `sample_rate_hz` | 12000 or 48000; 48 kHz is accepted only for drive-end metadata |
| `value_unit` | `unknown` |

Keeping `value_unit` unknown is intentional. The adapter does not silently convert local CWRU values into MotorPulse's synthetic acceleration units or claim a physical calibration it has not independently verified.

## Inspect one local file

```bash
python -m motorpulse.cwru \
  --input /private/local/cwru/105.mat \
  --metadata /private/local/cwru/105.metadata.json \
  --out /private/local/cwru/105-summary.json
```

After installation, the equivalent console command is:

```bash
motorpulse-cwru \
  --input /private/local/cwru/105.mat \
  --metadata /private/local/cwru/105.metadata.json \
  --out /private/local/cwru/105-summary.json
```

The output path must be new; existing files are not overwritten. The command performs no network request.

The report contains source filename, byte count, SHA-256, explicit test-condition metadata and bounded statistics for the selected vector: sample count, native mean, native RMS, native peak-to-peak, crest factor, declared sampling rate and derived window duration. It **does not** contain the raw sample vector or an absolute local source path.

The label block explicitly records:

- the user-reviewed seeded fault condition and optional fault diameter;
- `run_to_failure: false`;
- null failure time, failure probability and remaining useful life.

Do not reinterpret a seeded defect size as damage progression or fault severity over time.

## Supported MATLAB subset

The adapter is not a general MATLAB runtime. It accepts bounded MATLAB-v5 files containing the explicitly named channel as one real `double` vector. Both ordinary `miMATRIX` data and zlib-compressed `miCOMPRESSED` elements are supported. The reader rejects symlinks, oversized files/elements/decompressed data, duplicate target variables, complex/non-double arrays, multidimensional matrices, missing channels, non-finite values, malformed tags and unsupported top-level structures.

These limits are intentional fail-closed behavior. If a legitimate local source file uses an unsupported MAT structure, extend the parser with a handwritten fixture and a focused regression test instead of silently changing interpretation.

## Generate a local dataset card

After creating a summary report, generate a path-free dataset card:

```bash
python -m motorpulse.dataset_cards \
  --source cwru \
  --input /private/local/cwru/105-summary.json \
  --out /private/local/cwru/105-card.json
```

The run card records report/source hashes and explicit seeded-condition provenance. It intentionally omits native RMS, peak-to-peak, crest factor and all sample values so the card itself is metadata rather than a derived measurement dataset.

The packaged template is `motorpulse/cards/cwru-v1.json`. It states that publication remains local-only, redistribution is unresolved, fault conditions are seeded rather than run-to-failure, and there is no RUL label.

## Split/evaluation cautions

A CWRU MATLAB file is not automatically an independent machine just because its filename differs. Related channels, conditions or slices from one physical experiment can leak across train/test boundaries if treated as unrelated rows. Establish a documented physical grouping before using local summaries or features in a model experiment.

MotorPulse's existing healthy-only anomaly baseline currently targets the synthetic export contract, not CWRU measurements. MP-031 does not authorize cross-domain evaluation, supervised industrial claims or mixing CWRU seeded labels into the synthetic MotorPulse fault taxonomy without an explicit research protocol.

## Tests

All MP-031 tests generate **handwritten MATLAB-v5 bytes** in temporary directories. They do not download, embed or derive from CWRU measurements.

```bash
python -m unittest discover -s tests -p 'test_cwru.py' -v
python -m unittest discover -s tests -v
```

The tests cover compressed/uncompressed vectors, explicit metadata, seeded-vs-run-to-failure semantics, fail-closed MAT parsing, write-once CLI output, summary-only reports, path-free dataset cards and rights uncertainty.
