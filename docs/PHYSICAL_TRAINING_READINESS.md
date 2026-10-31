# Physical training-readiness contract (MP-061)

MP-061 is an offline review gate between local physical-data preparation and any future model-training implementation. It verifies that an MP-059 whole-asset split, the exact physical run cards behind that split, and the corresponding MP-060 evidence reviews form a coherent cohort.

`ready_for_review is not training authorization`. MP-061 does not fit a model, select a production threshold, score a physical machine, diagnose a fault, estimate failure probability, make a maintenance decision, publish physical data, or deploy software to hardware.

## Inputs

The readiness assessment consumes:

- one exact MP-059 physical split plan;
- every MP-059 run card referenced by that plan; and
- exactly one MP-060 evidence review for every run card.

All three layers are cryptographically/source bound. A changed card invalidates its MP-060 review, and a changed split plan invalidates its `plan_sha256`. MP-061 revalidates those bindings rather than trusting filenames or caller ordering.

## Split and leakage checks

MP-061 independently rechecks the MP-059 **asset-disjoint** partition contract:

- partitions must be exactly `train`, `validation`, and `test`;
- every supplied card and session must appear exactly once;
- every physical asset must appear in exactly one partition;
- partition card/session/asset membership must agree with the supplied run cards;
- partition counts must replay from the supplied cards; and
- duplicate card IDs, session IDs, or physical feature content are rejected.

A forged plan with a recomputed checksum is still rejected if it leaks one asset across partitions.

## Evidence policy

Every session requires independently reviewed:

- calibration evidence; and
- rights/privacy evidence.

For `unsupervised_anomaly`, MP-061 does not require a physical label/failure review. Unknown physical labels remain unknown.

For `supervised_failure`, every session must additionally have reviewed label/failure evidence from the MP-060 independent-evidence allowlist. **signal-derived truth is not allowed**. A signal anomaly, model output, threshold alarm, vibration pattern, temperature rise, or RPM behavior cannot silently become ground truth.

Missing required evidence is a deterministic readiness blocker. Invalid or tampered evidence manifests fail closed before blocker evaluation.

## Feature and sampling compatibility

The proposed cohort must use one physical feature version and one canonical sampling contract. A session with a different sampling rate/sample count is reported as blocked. A session with no successfully extracted physical feature records is also blocked.

MP-061 does not claim that matching sampling metadata proves sensor equivalence, installation equivalence, or domain transfer. Sensor/device provenance stays visible through the source-bound run cards and requires later experimental review before any training claim.

## Readiness states

A structurally valid cohort produces one of two states:

- `ready_for_review`: all MP-061 structural/evidence/readiness checks pass;
- `blocked`: the cohort is validly structured but has explicit policy blockers such as missing evidence, incompatible sampling, or no extracted records.

Blockers are sorted, unique, deterministic strings. Structural corruption, checksum mismatch, unknown cards/reviews, duplicate identities, or partition leakage raises an error instead of producing a misleading readiness report.

Even when the state is `ready_for_review`, MP-061 always writes:

- `redistribution_cleared = false`;
- `training_authorized = false`;
- `model_scoring_authorized = false`;
- `diagnosis_authorized = false`; and
- `rul_authorized = false`.

A later explicitly reviewed milestone must consume a ready assessment before physical training can even be implemented. That later work must define training-only preprocessing, validation-only selection, untouched held-out test evaluation, model-card claim limits, and rollback/reproducibility requirements.

## Preprocessing boundary

The readiness output pins the policy:

> fit preprocessing and thresholds on training assets only; use validation for selection and keep test assets untouched until final evaluation

MP-061 does not execute that policy because it does not train a model. It records the boundary for a later implementation.

## CLI

```bash
python -m motorpulse.physical_training_readiness \
  --split physical-split.json \
  --card run-a.json --card run-b.json --card run-c.json \
  --review review-a.json --review review-b.json --review review-c.json \
  --target-mode unsupervised_anomaly \
  --out physical-readiness.json
```

`--card` and `--review` are repeatable. Input order does not affect the deterministic assessment. Output is write-once; an existing output path is never overwritten.

The alternative target mode is `supervised_failure`, which only changes the evidence requirement. It still does not authorize or perform supervised training.

## Local-data and deployment boundary

Physical captures, derived physical features, run cards, evidence manifests, and readiness assessments remain local/private unless a separate rights review and publication process explicitly clears appropriate metadata. MP-061 itself always keeps redistribution closed.

MP-061 opens no serial port, creates no Wi-Fi/network listener, adds **no PLC** or actuator path, and provides no remote deployment or machine-control capability.

**MP-016 remains ON HOLD** for live sensors, edge/device transport, PLC integration, and remote deployment. Those capabilities require separate transport security, device identity, replay protection, operational failure handling, and independent machine-safety engineering.
