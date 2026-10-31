# Physical experiment preregistration gate (MP-063)

MP-063 freezes the first physical-data experiment design before any physical trainer exists. It consumes an exact MP-062 experiment bundle and revalidates that bundle against the full MP-061/059/060/058 source chain before producing a deterministic metadata-only preregistration.

A preregistration **does not train a model** and does not grant permission to train one. Its strongest successful state is `eligible_for_explicit_training_approval`. A later separately reviewed milestone must record any explicit training approval and must still revalidate this preregistration and its sources.

## First supported physical experiment

The first supported target is `unsupervised_anomaly` with the fixed candidate family `standardized_distance_baseline_v1`. This deliberately mirrors the transparent five-feature baseline shape already used for the synthetic research path without claiming that synthetic performance transfers to machinery.

The frozen numeric input allowlist is:

- `rms_g`
- `crest_factor`
- `band_80_400_rms_g`
- `temperature_c`
- `rpm`

Identity, provenance, quality state, timestamps, review metadata, labels, and failure evidence are not numeric model inputs.

## Partition firewall

MP-063 freezes the experiment so that model fitting and threshold construction are train-only:

- `fit_partition = train`
- `preprocessing_fit_partition = train`
- `threshold_partition = train`
- validation is `review_only_no_fit`
- `test_role = final_only_no_fit`

The threshold quantile is preregistered before training and must be between 0.90 and 0.999 inclusive. The deterministic seed is also preregistered. Neither validation nor test may be substituted as a fit, preprocessing, or threshold source by changing the preregistration JSON; validation recomputes the complete artifact from the protocol and exact source chain.

## Minimum evidence volume

The protocol must declare positive minimum extracted-record counts independently for train, validation, and test. MP-063 compares those preregistered minimums with the exact MP-062 partition contents.

If any partition is below its minimum, the artifact is still structurally valid but its state is `blocked`, with a deterministic blocker such as:

```text
insufficient_train_extracted_records:1<8
```

This is intentionally different from malformed or tampered inputs, which raise validation errors and produce no accepted preregistration.

## Source integrity

Before any preregistration is accepted, MP-063 calls the MP-062 validation contract again. That means the exact local feature bytes, canonical feature digests, run cards, split, reviews, and readiness decision must still agree.

A whitespace-only change to a feature JSONL changes the MP-062 exact file SHA-256 and therefore invalidates the previously preregistered source bundle even if the canonical scientific feature content remains identical.

The preregistration records only hashes, IDs, counts, the frozen design, and blockers. It contains no raw acceleration waveform, no feature values, and no local filesystem paths.

## Authorization boundary

Even when the state is `eligible_for_explicit_training_approval`, MP-063 always writes:

- `redistribution_cleared = false`
- `training_authorized = false`
- `model_scoring_authorized = false`
- `diagnosis_authorized = false`
- `rul_authorized = false`

Editing one of those fields to `true` invalidates the artifact. Eligibility means only that the exact bundle and frozen design satisfy the preregistration checks; it is not a training grant, model-performance result, diagnosis, failure probability, RUL estimate, or maintenance recommendation.

## Protocol JSON

A minimal first-experiment protocol is:

```json
{
  "protocol_version": "1.0.0",
  "model_family": "standardized_distance_baseline_v1",
  "threshold_quantile": 0.99,
  "seed": 17,
  "minimum_extracted_records": {
    "train": 8,
    "validation": 4,
    "test": 4
  }
}
```

The protocol schema is strict. Unknown fields, unsupported model families, invalid seeds, out-of-range quantiles, missing partitions, zero/negative minimums, and excessively large minimums fail closed.

## CLI

```bash
python -m motorpulse.physical_experiment_preregistration \
  --bundle physical-experiment-bundle.json \
  --readiness physical-readiness.json \
  --split physical-split.json \
  --card run-a.json --card run-b.json --card run-c.json \
  --review review-a.json --review review-b.json --review review-c.json \
  --feature features-a.jsonl --feature features-b.jsonl --feature features-c.jsonl \
  --protocol physical-experiment-protocol.json \
  --out physical-experiment-preregistration.json
```

The output is write-once. Reusing the same path is rejected rather than overwriting prior evidence.

## What MP-063 does not do

MP-063 does not fit preprocessing statistics, calculate anomaly thresholds, train weights/parameters, score validation/test records, compare models, diagnose a machine, estimate failure probability, estimate RUL, publish physical measurements, or make a maintenance decision.

It opens no serial port, creates no Wi-Fi/network listener, adds **no PLC** or actuator/control path, and adds no remote deployment capability.

**MP-016 remains ON HOLD** for live sensors, edge/device transport, PLC integration, and remote deployment. Hardware and operational control remain separate security and machine-safety work.
