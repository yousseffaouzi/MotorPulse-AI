# Physical model evaluation approval boundary (MP-067)

MP-067 adds a **pending request only** for the first held-out physical-model
evaluation step. It does not score any physical row and it does not grant
permission to score one.

The request is intentionally narrower than the MP-066 training authorization. It
binds the exact trained model and its complete upstream approval/source chain to a
proposed **validation partition only** scoring operation. The test partition remains untouched.

## What MP-067 freezes

The request revalidates the exact MP-066 model artifact, MP-065 training approval
record and separate human decision, MP-064 training request, MP-063
preregistration/protocol, MP-062 bundle, MP-061 readiness result, MP-059 split,
run cards, evidence reviews, and the exact MP-058 feature-file bytes.

It then freezes only these proposed operations:

- `score_validation_partition_with_frozen_model`
- `review_validation_scores_only`

The train partition is frozen with no rescore. Validation may be scored only after
a later, separate explicit approval record accepts the exact MP-067 challenge.
The test partition remains `untouched_no_score`.

## What the request does not authorize

MP-067 keeps all of the following false:

- validation scoring authorization
- test scoring authorization
- model refit authorization
- preprocessing refit authorization
- threshold recalibration authorization
- diagnosis authorization
- failure-probability authorization
- RUL authorization
- redistribution/publication clearance
- deployment authorization

There is **no refit or recalibration** in this milestone. The MP-066 threshold is
only identified as part of the frozen model provenance; MP-067 does not apply it
to validation rows.

The standardized-distance score remains an anomaly/review quantity. It is **not a failure probability**,
a diagnosis, a remaining-useful-life estimate, or evidence of field performance.

## Human approval boundary

Generating or displaying the request is not approval. A green CI run is not
approval. A generic `continue` is not approval. The request carries a deterministic
challenge hash and exact phrase so a later milestone can require a separately
authored decision bound to this precise model and scope.

Repository tests use synthetic physical-style fixtures only. Fixture requests or
decisions are non-operational and authorize no real dataset, device, person, or
deployment.

## Data and deployment boundary

Physical inputs and all artifacts derived from them remain local under
`local_only_do_not_redistribute`. MP-067 adds no network listener, remote upload,
ESP32/serial/Wi-Fi connection, PLC/actuator command path, or autonomous action.

MP-016 remains ON HOLD.

## Offline command

The request can be generated locally with:

```text
python -m motorpulse.physical_evaluation_approval_request \
  --model physical-model.json \
  --approval-record training-approval.json \
  --training-request training-request.json \
  --decision training-decision.json \
  --preregistration preregistration.json \
  --bundle bundle.json \
  --readiness readiness.json \
  --split split.json \
  --card run-card-a.json --card run-card-b.json --card run-card-c.json \
  --review review-a.json --review review-b.json --review review-c.json \
  --feature features-a.jsonl --feature features-b.jsonl --feature features-c.jsonl \
  --protocol protocol.json \
  --out validation-scoring-request.json
```

The output is write-once. Existing files are never overwritten.
