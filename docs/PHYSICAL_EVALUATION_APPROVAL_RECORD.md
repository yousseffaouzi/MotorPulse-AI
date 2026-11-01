# Physical validation-scoring approval record (MP-068)

MP-068 turns one exact MP-067 pending request into a narrow authorization record
only when a **separately authored human decision** matches the exact request ID,
request SHA-256, challenge SHA-256, and complete approval phrase.

The command itself does not score any physical row. It only validates and records
the decision. A generic instruction such as `continue` is not approval, and neither
are request generation, request display, repository fixture data, or green CI.

## Exact scope

A valid record authorizes only the two operations frozen by MP-067:

- `score_validation_partition_with_frozen_model`
- `review_validation_scores_only`

The record explicitly has `validation_scoring_authorized = true` while
`test_scoring_authorized = false`. The train partition remains frozen and cannot be
rescored. Model refit, preprocessing refit, and threshold recalibration remain
forbidden.

The approved capability is still offline, validation-only scoring with the exact
MP-066 model. It does not authorize diagnosis, failure probability, RUL,
redistribution/publication, deployment, network access, or hardware/control action.

## Human decision boundary

The decision artifact must contain:

- the exact MP-067 evaluation request ID
- the exact SHA-256 of that request
- the exact approval challenge SHA-256
- `approve_validation_scoring_only`
- the exact MP-067 approval phrase as the human affirmation
- a reviewer assertion
- an explicit UTC decision timestamp ending in `Z`

The reviewer assertion is **self-asserted and is not authenticated**. MP-068 also
records signature assurance as `none`; it does not claim a cryptographic signature,
organizational identity proof, or external authorization system.

Repository tests use synthetic physical-style fixture decisions. Those fixtures are
non-operational and authorize no real dataset, device, person, or deployment.

## Not a bearer token

The approval record is **not a standalone bearer token**. Any future validation
scorer must revalidate the exact MP-068 decision and record, the MP-067 request, the
MP-066 model, the MP-065 training approval chain, and the complete upstream source
artifacts and feature bytes before reading validation rows for scoring.

Copying the approval JSON alone is insufficient. Any stale, modified, or mismatched
request/model/source chain must fail closed.

## Scoring and claim boundary

MP-068 performs no scoring and produces no validation metric. The standardized
anomaly score remains a review quantity, not a diagnosis, not a failure probability,
and not a remaining-useful-life estimate.

The test partition remains untouched. No final-test authorization exists in MP-068.

## Data, deployment, and hardware boundary

Physical inputs and their derived artifacts remain local under
`local_only_do_not_redistribute`. There is no remote upload, network listener,
ESP32/serial/Wi-Fi connection, PLC/actuator command path, deployment path, or
autonomous action.

MP-016 remains ON HOLD.

## Offline command

A separately authored decision can be validated and recorded locally with:

```text
python -m motorpulse.physical_evaluation_approval_record \
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
  --out validation-scoring-approval-record.json
```

The output is write-once and existing files are never overwritten.
