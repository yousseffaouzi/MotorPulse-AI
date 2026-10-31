# Physical experiment bundle audit (MP-062)

MP-062 closes the gap between a metadata-level MP-061 readiness decision and the exact local MP-058 feature files that a future training experiment would read. It is a **metadata-only** audit layer and **does not fit a model**.

A bundle is accepted only when the supplied MP-061 assessment can be recomputed exactly from its MP-059 split/run cards and MP-060 evidence reviews and the assessment state is `ready_for_review` with no blockers.

## Why bind the feature files again

MP-059 run cards already contain the canonical `features_sha256` for each acquisition session. MP-062 reopens every local feature JSONL, validates every row using the MP-059 contract, recomputes that canonical digest, and matches it to exactly one ready run card.

MP-062 also records a SHA-256 over the **exact feature bytes** currently stored in each local JSONL. This creates two distinct protections:

- `features_sha256` binds the canonical scientific feature content to the MP-059 run card; and
- `feature_file_sha256` binds the exact audited file bytes for later re-verification.

A semantically equivalent file with different whitespace can retain the canonical feature digest but will have a different exact file digest. Re-validating an existing bundle against that changed file therefore fails.

## End-to-end source revalidation

Before auditing files, MP-062 recomputes MP-061 readiness from:

- the exact MP-059 split plan;
- all exact MP-059 run cards; and
- exactly one MP-060 evidence review per card.

The recomputed readiness object must be byte-semantically identical to the supplied readiness JSON. This means a bundle cannot bypass the MP-059 asset-disjoint split, MP-060 independent-evidence requirements, or MP-061 readiness blockers by supplying a stale or edited assessment.

Only `ready_for_review` can be bundled. `blocked` cohorts are rejected.

## Feature-file checks

Every ready run card must match exactly one local feature file, independent of caller path order. MP-062 rejects:

- missing or extra feature files;
- duplicate feature content or duplicate exact file bytes;
- a feature file not present in the ready cohort;
- semantic feature tampering;
- symlinked, malformed, empty, oversized, or invalid JSONL;
- changed asset or device identity;
- changed row/status counts;
- changed sampling contract; and
- changed sensor/firmware provenance.

Raw acceleration waveforms are not part of the MP-058 feature-row schema and cannot appear in a valid MP-062 source file.

## Manifest contents

The output contains only source metadata needed to re-audit the experiment boundary:

- readiness assessment ID and SHA-256;
- split plan SHA-256 and target mode;
- train/validation/test membership inherited from the verified MP-059 plan;
- card/session/asset IDs;
- canonical feature digest;
- exact feature-file digest; and
- record/extracted/abstained counts.

The manifest contains no raw waveform, no derived feature values, and no local filesystem path. It remains safe to treat as provenance metadata, not as redistribution clearance for the underlying physical measurements.

## Authorization remains closed

Even a valid MP-062 bundle always writes:

- `redistribution_cleared = false`;
- `training_authorized = false`;
- `model_scoring_authorized = false`;
- `diagnosis_authorized = false`; and
- `rul_authorized = false`.

A bundle proves that the exact local feature files correspond to the reviewed cohort. It is not permission to fit preprocessing, thresholds, or models and is not evidence of model performance.

## CLI

```bash
python -m motorpulse.physical_experiment_bundle \
  --readiness physical-readiness.json \
  --split physical-split.json \
  --card run-a.json --card run-b.json --card run-c.json \
  --review review-a.json --review review-b.json --review review-c.json \
  --feature features-a.jsonl --feature features-b.jsonl --feature features-c.jsonl \
  --out physical-experiment-bundle.json
```

The `--card`, `--review`, and `--feature` inputs are repeatable. Feature path order does not affect output because files are matched by canonical feature digest. Output is write-once and never overwrites an existing path.

## Data and deployment boundary

Physical captures and derived feature files stay local/private. MP-062 provides no publication or redistribution permission, no failure-probability claim, no diagnosis, no RUL, and no maintenance decision.

MP-062 opens no serial port, creates no Wi-Fi/network listener, adds **no PLC** or actuator/control path, and provides no remote deployment capability.

**MP-016 remains ON HOLD** for live sensors, edge/device transport, PLC integration, and remote deployment. Those capabilities remain a separate security and machine-safety phase.
