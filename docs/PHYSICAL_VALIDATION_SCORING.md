# Physical validation scoring (MP-069)

MP-069 adds the first physical-model scoring step. It is deliberately limited to
the **validation partition only** and is unreachable through the public workflow
unless the **full MP-068 approval chain** revalidates against the exact decision,
MP-067 request, MP-066 model, training approval chain, split, bundle, run cards,
evidence reviews, protocol, and physical feature-file bytes.

A copied approval record is not enough. The scorer revalidates the complete chain
before producing a result.

## Frozen model only

MP-069 uses the exact center, effective scales, and train-derived threshold already
stored in the MP-066 model. There is **no refit or recalibration**:

- no model fit or refit
- no preprocessing fit or refit
- no threshold selection or recalibration
- no training-partition rescoring
- no test-partition scoring

The threshold comparison is the preregistered strict `score > threshold` rule.
Crossing it creates only a review flag.

## Review-only meaning

A **review flag is not a diagnosis**. The standardized-distance score is not a
failure probability, remaining-useful-life estimate, fault classification, field
performance guarantee, or maintenance command.

For every validation row whose physical feature extraction abstained, MP-069 keeps
the row abstained: `score` and `review_flag` are `null`. It never invents a score
for unavailable or invalid physical measurements.

## Test boundary

The **test partition remains untouched** for scoring. MP-069 has no partition
selector and cannot be redirected to test data. Its result records
`test_rows_consumed = 0` and `test_scoring_authorized = false`.

A future final-test milestone must require its own explicit request and separate
human approval; validation success alone must not unlock test scoring.

## Output and provenance

The deterministic write-once JSON result contains only:

- row identity metadata (`card_id`, sequence, input-frame SHA-256)
- validation anomaly score or explicit abstention
- review flag derived from the frozen strict threshold comparison
- bounded validation counts
- exact model, MP-068 approval-record, and MP-067 request provenance
- explicit false downstream-claim and deployment fields

It does not contain raw vibration samples, physical feature values, waveforms, or
local filesystem paths. Physical inputs and derived artifacts remain
`local_only_do_not_redistribute`.

Repository tests use synthetic physical-style fixtures and fixture approval
decisions only. Those fixtures are non-operational and authorize no real dataset,
device, person, deployment, or test-partition scoring.

## Offline command

```text
python -m motorpulse.physical_validation_scorer \
  --evaluation-approval-record validation-scoring-approval-record.json \
  --evaluation-request validation-scoring-request.json \
  --evaluation-decision validation-scoring-decision.json \
  --model physical-model.json \
  --training-approval-record training-approval.json \
  --training-request training-request.json \
  --training-decision training-decision.json \
  --preregistration preregistration.json \
  --bundle bundle.json \
  --readiness readiness.json \
  --split split.json \
  --card run-card-a.json --card run-card-b.json --card run-card-c.json \
  --review review-a.json --review review-b.json --review review-c.json \
  --feature features-a.jsonl --feature features-b.jsonl --feature features-c.jsonl \
  --protocol protocol.json \
  --out validation-result.json
```

The output is write-once and existing files are never overwritten.

## Hardware and deployment boundary

MP-069 adds no ESP32/serial/Wi-Fi listener, network upload, remote deployment,
PLC/actuator command path, or autonomous action. MP-016 remains ON HOLD.
