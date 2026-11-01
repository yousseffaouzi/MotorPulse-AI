# Physical final-test scoring approval boundary (MP-070)

MP-070 adds a **pending request only** for the first physical final-test scoring
step. It does not read or score test rows and it does not grant permission to do
so.

The request is bound to the **exact MP-069 validation result** and revalidates that
result against the complete MP-068/067/066/065/064/063/062/061/059/060/058
approval and source chain before producing the request.

## Frozen final-test scope

MP-070 requests only:

- `score_test_partition_with_frozen_model`
- `review_final_test_scores_only`

The MP-066 model, preprocessing center/scales, and train-derived threshold remain
frozen. The training partition remains frozen and unscored. The completed
validation result is frozen and may not be rescored. There is **no refit or
recalibration**.

The test partition can be scored only after a later, separately authored human
decision accepts the exact MP-070 challenge. Until then,
`test_scoring_authorized = false`, `test_scoring_completed = false`, and
`test_rows_consumed = 0`.

## Approval boundary

Generating or displaying this request is not approval. Validation success is not
test approval. A green CI run is not approval. A generic `continue` is not approval.
The deterministic challenge hash and exact phrase exist so a later milestone can
require a separately authored decision bound to this exact validation result,
model, and final-test scope.

Repository tests use synthetic physical-style fixtures and fixture decisions only.
They authorize no real physical dataset, device, person, final-test scoring, or
deployment.

## Claim boundary

MP-070 does not produce final-test scores or metrics. It does not authorize
train/validation rescoring, model or preprocessing refit, threshold recalibration,
diagnosis, failure probability, remaining-useful-life estimation, publication,
redistribution, deployment, or autonomous maintenance action.

A future final-test scorer must continue to treat the frozen standardized-distance
score as a review quantity, not a diagnosis or failure probability.

## Data and hardware boundary

Physical inputs and derived artifacts remain local under
`local_only_do_not_redistribute`. MP-070 adds no remote upload, network listener,
ESP32/serial/Wi-Fi connection, PLC/actuator path, deployment path, or autonomous
action.

MP-016 remains ON HOLD.

## Offline command

```text
python -m motorpulse.physical_final_test_approval_request \
  --validation-result validation-result.json \
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
  --out final-test-request.json
```

The output is deterministic and write-once. Existing files are never overwritten.
