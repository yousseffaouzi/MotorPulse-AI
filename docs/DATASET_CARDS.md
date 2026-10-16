# MP-032 — Dataset cards: lineage, use and scientific limitations

MotorPulse AI ships three **versioned, machine-readable dataset-card templates**:

| Template | Data type | Evidence / publication policy |
|---|---|---|
| [synthetic-v1.json](../motorpulse/cards/synthetic-v1.json) | Programmatically simulated motor feature events | Source code and generated output only; no real sensor data |
| [ims-v1.json](../motorpulse/cards/ims-v1.json) | Third-party IMS experimental bearing records, *local inspection metadata only* | **No original IMS data inspected or committed.** Archive-specific rights and reuse of derived data remain **unverified** |
| [cwru-v1.json](../motorpulse/cards/cwru-v1.json) | Third-party CWRU seeded-fault bearing records, *local inspection metadata only* | **No CWRU measurements downloaded or committed.** Original/derived redistribution rights remain **unverified** |

All three templates have `card_version="1.0.0"`, `instance_kind="template"`, `run_provenance=null`. They describe dataset **types**, not fictional completed runs. A real local **run card** is generated only from a source file or directory that already exists and passes its source-specific validator.

Dataset cards **do not establish permission** to download, use or redistribute outside the applicable source terms. NASA's public IMS listing is not itself evidence that all third-party donated data and derivatives are public domain, and CWRU's public download pages are not treated as an explicit redistribution license. See [DATA_PROVENANCE.md](DATA_PROVENANCE.md), the original [IMS source card](sources/ims-bearings.source.json), and the [CWRU source card](sources/cwru-bearings.source.json).

## 1. Run-specific synthetic card

First create a simulated event export, then bind its exact provenance:

```bash
mkdir -p datasets

python -m motorpulse.export --out-dir datasets/card-demo \
  --ticks 12 --seed 42 --format both \
  --config docs/examples/operations-v1.json

python -m motorpulse.dataset_cards --source synthetic \
  --input datasets/card-demo --out datasets/card-demo/dataset-card.json
```

The installed entry point `motorpulse-card` accepts the same flags. The card generator reuses [MP-029's EDA validator](EDA.md), which checks the export manifest and source file **SHA-256 plus byte lengths**, validates the JSONL events and their sensor-quality/health consistency, and refuses CSV-only export. It additionally checks that the expanded export configuration hashes to `config_sha256`.

A run card includes its **actual** `export_id`, `config_sha256`, `model_source_sha256`, JSONL digest, every output file digest, seed, ticks, events, asset count, virtual start/end UTC, sample rate and sample count. It retains the `labels`, `license`, `known_limitations`, `intended_uses` and `excluded_uses` of the versioned template.

The synthetic generator uses 1024 Hz, 1024 acceleration samples (g), 1-second nominal windows, illustrative fault amplitudes, fixed scenarios and uncalibrated threshold alerts. The label fields explicitly distinguish:

- **`motor_fault`** — controlled **synthetic** scenario and severity, not a measured machine defect.
- **`sensor_quality`** — programmatically injected `good`/`missing`/`outlier` condition, not an instrument-health detector.
- **`health`** — *uncalibrated rule output*, not a trained model or a failure probability.
- `failure_probability` and `remaining_useful_life` are **null**, because no valid prognostic model exists.

The real wall-clock `manifest.created_at_utc` is intentionally **not copied** into the generated card: `run_provenance.generated_at_utc=null` with an explanation. Same generator code, seed, configuration and source records produce **identical run cards** across output directories. This does not guarantee bit-identical behavior across all Python versions or physical reality. See [DATASET.md](DATASET.md) and [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md).

**License precision:** The MotorPulse AI **code** is MIT licensed. The project currently does **not** claim that a separate explicit MIT/CC0/CC-BY data license has been granted for generated exports; the template uses `dataset_specific_license=null` and `license_status="not_separately_specified"`. Do not make claims about rights in independently supplied or derivative third-party inputs.

## 2. Local IMS inspection card — no archive redistribution

After independently acquiring and **lawfully** inspecting an IMS-style set, create the local report using [MP-009](IMS_INGESTION.md), then generate a **local-only** card:

```bash
python -m motorpulse.ims \
  --input-dir tests/fixtures/ims_style_synthetic \
  --test-set 2 --sample-rate-hz 8 \
  --expected-samples 4 --expected-channels 4 \
  --manifest /tmp/ims-inspection-for-card.json

python -m motorpulse.dataset_cards --source ims \
  --input /tmp/ims-inspection-for-card.json \
  --verify-files --out /tmp/ims-local-dataset-card.json
```

**The included fixtures are entirely handwritten numerical examples, not IMS data.** For actual personal archives, keep all inputs and generated cards in untracked local storage such as `data/external/` or `data/reports/`, and review the applicable terms before accessing or using the archive.

The IMS card reuses the [MP-028 validator](IMS_VALIDATION.md). It records the source card ID, run/test set, sample and channel counts, explicitly *user-declared* sampling rate, sample count and native unit, unknown timestamp timezone, optional user-supplied acquisition/archive hash and quality-flag counts. `--verify-files` optionally recomputes hashes of local text recordings; otherwise the card honestly reports `file_hashes_rechecked=false`. The importer validates report structure but cannot independently certify an original archive, acquisition rate, geometry, source terms or test-set independence.

A local IMS card intentionally does **not** embed raw samples, time-indexed channel features, absolute local file paths or actual per-record waveform digests. Its `inspection_report_sha256` fingerprints the *local metadata report*, not a supposedly known original upstream ZIP. The original source archive digest remains null unless a user explicitly supplies it; even then it is labeled **user-supplied**.

The IMS template and run cards preserve:
- Catalog license badge `other-license-specified`, **dataset_specific_license=null**, `rights_review.status="hold"`, and `derived_publication_cleared=false`.
- Reported end-of-run failures in public background literature **do not** imply known per-window fault onset, healthy/fault labels or RUL. These remain **null**.
- Original sampling rate, units, physical bearing map and timezone are **not yet verified by this project**. User-declared local run values are explicitly separate from the global template's null attributes.
- Distinct source-run and channel groups; preserve all related windows in the same partition. See [SPLITS.md](SPLITS.md) (MP-030).
- Measurement quality flags from MP-028 (flatline, high crest, cadence, unverified units/mapping) are **review prompts**, not proven fault diagnoses.

Correct credit from the NASA PCoE repository: J. Lee, H. Qiu, G. Yu, J. Lin, and Rexnord Technical Services (2007), IMS University of Cincinnati, *Bearing Data Set*, NASA Prognostics Data Repository, NASA Ames Research Center. The repository asks for both the original contributors and NASA repository to be acknowledged.

## 3. Local CWRU seeded-fault card — no measurement redistribution

After inspecting one **user-supplied local** CWRU MATLAB-v5 file with explicit metadata, generate a metadata-only run card:

```bash
python -m motorpulse.cwru \
  --input /private/local/cwru/105.mat \
  --metadata /private/local/cwru/105.metadata.json \
  --out /private/local/cwru/105-summary.json

python -m motorpulse.dataset_cards --source cwru \
  --input /private/local/cwru/105-summary.json \
  --out /private/local/cwru/105-card.json
```

The CWRU run card records the source/report SHA-256 values, basename, byte count, explicitly selected channel, bearing location, seeded fault type/diameter/outer-race position, load, sample rate and sample count. It deliberately omits native RMS, peak-to-peak, crest factor and all sample values, so the card is provenance metadata rather than a redistributed measurement dataset.

CWRU fault records are documented as seeded single-point **EDM** conditions. The card therefore pins `run_to_failure=false`, null failure time and null remaining useful life; it must not be interpreted as a degradation trajectory or RUL benchmark. Fault/channel/load/rate metadata are explicit local inputs and are never inferred from a numeric MAT filename.

The project records CWRU `rights_status="unverified_for_redistribution"` and `publication_status="local_only_do_not_redistribute"`. The official pages reviewed provide experiment metadata and downloads but did not establish an explicit dataset redistribution license for this project. See [CWRU_INGESTION.md](CWRU_INGESTION.md).

## 4. Read and validate cards programmatically

```python
from motorpulse.dataset_cards import (
    template_card, validate_card, synthetic_run_card, ims_run_card, cwru_run_card
)

synthetic_template = template_card("synthetic")
ims_template = template_card("ims")
cwru_template = template_card("cwru")
validate_card(synthetic_template)
validate_card(ims_template)
validate_card(cwru_template)

# Once local input exists, without copying data into this repository:
# generated = synthetic_run_card("datasets/card-demo")
# local_ims = ims_run_card("data/external/ims-inspection.json", verify_files=True)
# local_cwru = cwru_run_card("data/external/cwru-summary.json")
```

The templates are bundled as Python package data so `motorpulse-card` works from installed wheels and from a local checkout. `motorpulse.dataset_cards.validate_card` enforces the project-specific v1 structure, conservative source/label claims, and source-bound SHA-256 metadata. It is **not** a legal audit and does **not** guarantee the factual correctness of third-party source assertions.

Cards are UTF-8 JSON, generated with **write-once exclusive-create** output (existing files are never overwritten). The local CLI does not contact an external network service. A static template can be compared to its source file `motorpulse/cards/*.json`; run cards are generated from *actually verified* local inputs.

The dataset-card design follows the broad documentation questions described in [Datasheets for Datasets](https://arxiv.org/abs/1803.09010): motivation, composition, collection, preprocessing, intended use and maintenance. These are guidelines, **not** an external validation/certification of MotorPulse AI. See also [Hugging Face's dataset card documentation](https://huggingface.co/docs/hub/datasets-cards).

## 5. Related milestones and data leakage warnings

- **MP-008** — [synthetic export](DATASET.md): manifest, seed and source/config digests, null-safe feature events.
- **MP-027** — [third-party provenance](DATA_PROVENANCE.md): actual IMS donor, official download URLs, citation and rights **HOLD**.
- **MP-009** — [user-provided IMS-style ingestion](IMS_INGESTION.md): no downloads and no invented fault labels.
- **MP-028** — [native-unit IMS validation](IMS_VALIDATION.md): optional hash rechecks, review-only quality flags and train-only feature scaling.
- **MP-029** — [exploratory reports](EDA.md): synthetic missingness, labels, descriptive statistics, local-only IMS summaries.
- **MP-030** — [leakage-resistant split planning](SPLITS.md): hold out *entire generator/IMS source runs*. Do **not** randomly split adjacent windows, use held-out data to choose scalers/thresholds, or train on repeated seed/config/run identities.
- **MP-031** — [local-only CWRU adapter](CWRU_INGESTION.md): seeded EDM fault metadata stays distinct from run-to-failure/RUL truth; no CWRU measurements are bundled or redistributed.

Dataset-card generation itself does not fit an ML model. MP-011 adds [held-out synthetic detection evaluation](EVALUATION.md), comparing learned anomaly alerts and original rule outputs without implying actual field predictive accuracy. MP-010 separately implements the first [healthy-trained synthetic anomaly baseline](ANOMALY_BASELINE.md), consuming authoritative MP-030 source-run splits and matching source-card provenance. Its output is an uncalibrated unusualness score, **not** a validated failure probability, remaining useful life or real machinery generalization. Next ML development should make model cards and evaluations consume both the split manifest and these dataset cards, preventing ambiguous provenance and label claims.

## 6. Tests and limitations

```bash
python -m unittest discover -s tests -p 'test_dataset_cards.py' -v
python -m unittest discover -s tests -p 'test_cwru.py' -v
python -m unittest discover -s tests -v
```

The original 16 dataset-card tests use software-generated MotorPulse datasets and **handwritten fake IMS-style samples** only. MP-031 adds separate CWRU contracts built from handwritten MATLAB-v5 bytes; they do not contain original or derived CWRU measurements. Together these tests exercise contract validation, rights/label boundaries, reproducible identities, corrupt inputs, local-only cards and CLI non-overwrite behavior.

**Known limits:** A static card cannot guarantee its linked archive license or contents, and an individual run card cannot substitute for a rigorous run-level evaluation, signal calibration study or physical diagnostic validation. The cards are concise provenance documents, not peer-reviewed data quality reports, liability waivers, maintenance recommendations or licenses.
