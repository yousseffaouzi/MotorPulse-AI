# Physical experiment operator guide (MP-077)

This is the navigation and stop/go checklist for the offline physical-data
research workflow on the development branch. The published v0.1.1 release is
a synthetic research lab; this guide describes later software on main.
No actual motor capture or physical-model evaluation is established by the
repository's generated fixture tests. The localhost dashboard remains synthetic.

## 1. Before starting

- Use Python 3.11–3.13 and a trusted local machine. See [installation](INSTALL.md).
- Keep original captures, derived rows, approvals and results in private local
  storage outside the repository. Preserve originals, hashes and backups.
  All physical artifacts remain `local_only_do_not_redistribute`.
- Use independently reviewed calibration and rights/privacy records. For
  label-based claims obtain independent machine-state evidence; never infer
  truth from the same vibration, RPM, temperature or anomaly scores.
- Keep a stable identity for each physical asset, device and acquisition
  session. Changes in sensor/firmware provenance require separate sessions.
- Plan at least three distinct physical assets for the asset-disjoint split.
  One motor, however many windows or sessions it produces, can demonstrate
  acquisition and feature extraction but cannot satisfy this experiment split.
  Three is a structural minimum, not statistical adequacy. Preregister
  sufficient independent assets, conditions and windows for the research goal.

## 2. Capture and prepare the cohort

The commands are local-file tools. Run them from the repository root with
explicit paths in an existing private working directory. The short filenames
below are placeholders for user-supplied files, not included real data.
The linked stage guides contain the full arguments and exact JSON contracts;
use `python -m motorpulse.<module> --help` for the corresponding CLI.
Outputs are write-once; choose a new path rather than overwrite evidence.

For each acquisition session, start with an already captured v1 JSONL:

```bash
python -m motorpulse.sensor_gateway capture.jsonl --out-report capture-report.json
python -m motorpulse.physical_features capture.jsonl --out-features features.jsonl --out-report features-report.json
python -m motorpulse.physical_dataset card --features features.jsonl --report features-report.json --session-id session-a --out run-card.json
```

The gateway verifies capture structure, ordering, provenance and hashes.
The current extractor requires good channels and a 1024 Hz, 1024-sample
vibration window; incompatible/poor-quality frames abstain. The tiny
repository example is structural fixture data, not an actual measurement.
See [capture contract](SENSOR_GATEWAY.md),
[feature extraction](PHYSICAL_FEATURES.md) and [run cards](PHYSICAL_DATASET.md).

| Stage | Module or subcommand | Output / stop condition |
|---|---|---|
| MP-059 [whole-asset split](PHYSICAL_DATASET.md) | physical_dataset split | Split plan; reject fewer than three assets, duplicate sessions or leakage |
| MP-060 [independent evidence](PHYSICAL_EVIDENCE.md) | physical_evidence | One review per exact card; no training grant |
| MP-061 [readiness](PHYSICAL_TRAINING_READINESS.md) | physical_training_readiness | Continue only if ready_for_review with no blockers |
| MP-062 [bundle](PHYSICAL_EXPERIMENT_BUNDLE.md) | physical_experiment_bundle | Bind exact raw and canonical feature hashes |
| MP-063 [preregistration](PHYSICAL_EXPERIMENT_PREREGISTRATION.md) | physical_experiment_preregistration | Continue only if eligible_for_explicit_training_approval with no blockers |

For this first experiment choose unsupervised_anomaly and the fixed
standardized_distance_baseline_v1 family. The five features are rms_g,
crest_factor, band_80_400_rms_g, temperature_c and rpm. Freeze the seed,
train-only threshold quantile and minimum extracted-record counts before
requesting approval. The example protocol in MP-063 is a structural example,
not a scientifically sufficient sample-size recommendation.

## 3. Three separate authorization gates

Never generate approval decisions on behalf of a reviewer. Each request is
pending until an independently authored human decision matches its exact
request ID, digest, challenge and full affirmation. A generic instruction to
continue, green CI, an example or fixture decision is not real authorization.
Identity is self-asserted and decisions are unsigned; independently establish
reviewer identity and actual authorization. A matching JSON file is not
authenticated consent.

| Stage | Module | Result |
|---|---|---|
| MP-064 [training request](PHYSICAL_TRAINING_APPROVAL_REQUEST.md) | physical_training_approval_request | Pending training-only request |
| MP-065 [training record](PHYSICAL_TRAINING_APPROVAL_RECORD.md) | physical_training_approval_record | Exact offline training-only approval |
| MP-066 [training](PHYSICAL_OFFLINE_TRAINING.md) | physical_offline_trainer | Frozen train-only fit and threshold |
| MP-067 [validation request](PHYSICAL_MODEL_EVALUATION_APPROVAL.md) | physical_evaluation_approval_request | Pending validation-only request |
| MP-068 [validation record](PHYSICAL_EVALUATION_APPROVAL_RECORD.md) | physical_evaluation_approval_record | Exact validation-only approval |
| MP-069 [validation scoring](PHYSICAL_VALIDATION_SCORING.md) | physical_validation_scorer | Frozen-model validation scores |
| MP-070 [final-test request](PHYSICAL_FINAL_TEST_APPROVAL.md) | physical_final_test_approval_request | Pending test-only request |
| MP-071 [final-test record](PHYSICAL_FINAL_TEST_APPROVAL_RECORD.md) | physical_final_test_approval_record | Exact final-test-only approval |
| MP-072 [final-test scoring](PHYSICAL_FINAL_TEST_SCORER.md) | physical_final_test_scorer | Frozen-model test scores |
| MP-073 [reporting](PHYSICAL_EXPERIMENT_REPORT.md) | physical_experiment_report | Descriptive local report |

After every stage, retain the exact inputs and outputs. Stop on an integrity
error, missing evidence, blocked state or absent/mismatched approval. Do not
edit hashes, approvals, cards, labels or split assignments to bypass a gate.
If a reviewed source changes, start a new appropriately reviewed chain rather
than silently repairing the old one. Never reuse test results to tune the
current experiment. Validation and test cannot fit, recalibrate or refit.

## 4. Manifest-driven execution

[MP-074 workflow](PHYSICAL_WORKFLOW.md) defines one strict JSON manifest
containing the explicit local artifact paths. Begin with the training-only
example from that guide and add the evaluation/final-test artifacts only as
their separate requests and decisions are reviewed. Each invocation executes
one stage, and none creates a decision or automatically proceeds to another.

```bash
python -m motorpulse.physical_workflow --manifest workflow.json --stage train --out physical-model.json
python -m motorpulse.physical_workflow --manifest workflow.json --stage validation --out validation-result.json
python -m motorpulse.physical_workflow --manifest workflow.json --stage test --out final-test-result.json
python -m motorpulse.physical_workflow --manifest workflow.json --stage report --out experiment-report.md --format markdown
```

These are separate commands with mandatory stops between them, not a script
to run unattended. Use the linked manifest guide for the exact keys.

## 5. Integrity and storage

MP-075 computes raw and canonical digests from one bounded read.
[MP-076 snapshots](PHYSICAL_FEATURE_SNAPSHOTS.md) capture private temporary
feature copies for fitting, scoring and their replay validators. The limit
is 256 MiB per file and 1 GiB per cohort. Provide sufficient private temporary
disk capacity. Ordinary exit cleans up copies; crashes may leave files and
deletion is not secure erasure. Capture is not atomic across the filesystem,
metadata is not protected against in-process mutation, and hostile local
operators are outside the trust model.

Full integrity replay reads all partitions and recomputes the original
train-only fit and prior validation scores when needed. Test data is not
cryptographically sealed; no test values enter fitting or validation scoring.
There is no global one-shot holdout ledger. A new invocation rechecks the
current source bytes.

## 6. Interpret results conservatively

Record the model/source fingerprints, independent asset/session counts,
scored and abstained windows, operating regimes and limitations. Report
validation and test separately. Window counts are not independent asset
counts; flag fractions are not verified fault rates or false-alarm rates.
No diagnosis, maintenance decisions, failure probability, or RUL can be
claimed from this unsupervised workflow. Synthetic benchmark metrics cannot
be transferred to physical data. See [reporting](PHYSICAL_EXPERIMENT_REPORT.md).

## 7. Hardware boundary

MP-016 remains ON HOLD. This guide does not add firmware, serial acquisition,
device networking, live dashboard ingestion, PLC, actuation or remote
deployment. A separately reviewed low-voltage, guarded bench acquisition
plan must precede any connection to physical equipment. Do not use the
localhost research API to control machinery. See [security](SECURITY.md)
and [sensor gateway](SENSOR_GATEWAY.md).
