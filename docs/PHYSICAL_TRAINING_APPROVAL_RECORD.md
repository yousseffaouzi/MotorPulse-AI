# Physical training approval record (MP-065)

MP-065 records a narrow authorization for one exact MP-064 request **only after** a separately authored human decision is supplied. It revalidates the MP-064 request and the complete MP-063/062/061/059/060/058 source chain before it can derive an approval record.

MP-065 does **not** create the human decision and does not train a model. CI success, request generation, or request display is not approval. A generic instruction such as `continue` is not approval.

## Separate human decision artifact

The MotorPulse command requires a `--decision` JSON file that must already exist. The command has no `--approve`, `--phrase`, `--reviewer`, or similar option that could manufacture the decision on the caller's behalf.

The decision contract is:

```json
{
  "approval_decision_version": "1.0.0",
  "request_id": "<exact MP-064 request_id>",
  "request_sha256": "<canonical SHA-256 of the exact MP-064 request>",
  "approval_challenge_sha256": "<exact MP-064 challenge>",
  "decision": "approve_offline_training_only",
  "human_affirmation": "<exact MP-064 APPROVE ... CHALLENGE ... phrase>",
  "reviewer_assertion": "<human-supplied reviewer identifier>",
  "decided_at_utc": "<explicit UTC timestamp ending in Z>"
}
```

The exact `human_affirmation` must equal the approval phrase in the MP-064 packet byte-for-byte as a JSON string value. Abbreviations, paraphrases, a bare `APPROVE`, or conversational instructions do not satisfy the contract.

The `reviewer_assertion` is **self-asserted and is not authenticated**. MP-065 has no account login, cryptographic signature, key management, hardware security module, or independent identity service. The UTC timestamp is also supplied by the reviewer and is syntactically validated, not independently time-attested. Those limitations are preserved explicitly in the output.

## Exact source and scope binding

Before recording approval, MP-065 revalidates:

1. the exact MP-064 request;
2. the MP-063 preregistration;
3. the MP-062 experiment bundle;
4. the MP-061 readiness assessment;
5. the MP-059 physical asset split;
6. all MP-060 evidence reviews and run cards;
7. every bound MP-058 feature file byte-for-byte through the upstream contracts; and
8. the MP-063 protocol.

A changed feature byte, stale request, altered request hash, different challenge, broadened operation, or edited upstream authorization field invalidates the approval chain.

The approved capability is fixed to:

```text
offline_training_only
```

and the approved operations remain exactly those requested by MP-064:

- fit preprocessing on `train`;
- fit the preregistered candidate model on `train`;
- derive the preregistered threshold on `train`.

Validation remains review-only/no-fit and test remains final-only/no-fit. An approval record cannot add validation/test fitting, held-out threshold tuning, general model scoring, deployment, diagnosis, RUL, publication, PLC control, or any other capability.

## Approval record boundary

A valid MP-065 record has:

```text
approval_state = approved_for_offline_training_only
training_authorized = true
model_scoring_authorized = false
diagnosis_authorized = false
rul_authorized = false
redistribution_cleared = false
deployment_authorized = false
reviewer_identity_assurance = self_asserted_not_authenticated
decision_signature_assurance = none
```

`training_authorized = true` means only that the exact preregistered offline fitting operations may be passed to a future physical-training implementation. It does not authorize scoring new physical data, field diagnosis, failure probability, RUL, alerting, maintenance action, publishing measurements, networking, deployment, or equipment control.

The record deliberately omits the raw approval phrase. It retains the request/challenge bindings and a canonical SHA-256 of the separate decision artifact.

The MP-065 record is **not a standalone bearer token**. Any future trainer must require and revalidate the approval record together with the original MP-064 request, the separately authored human decision, and the same complete upstream source chain. Possession or copying of the record alone must not authorize training.

## CLI

After a human has independently authored the decision JSON for the exact request, the record can be validated and written with:

```bash
python -m motorpulse.physical_training_approval_record \
  --request physical-training-approval-request.json \
  --decision human-training-decision.json \
  --preregistration physical-experiment-preregistration.json \
  --bundle physical-experiment-bundle.json \
  --readiness physical-readiness.json \
  --split physical-split.json \
  --card run-a.json --card run-b.json --card run-c.json \
  --review review-a.json --review review-b.json --review review-c.json \
  --feature features-a.jsonl --feature features-b.jsonl --feature features-c.jsonl \
  --protocol physical-experiment-protocol.json \
  --out physical-training-approval-record.json
```

The output is write-once. Existing files and symlink outputs are rejected rather than overwritten.

## Test fixtures are not operational approval

Repository tests use synthetic/local temporary fixture decisions solely to prove the validator behavior. A fixture reviewer name, fixture timestamp, generated test phrase, or passing test run authorizes no real physical dataset and no future experiment. Operational approval still requires a separately authored decision for the exact real MP-064 request produced from the reviewed local physical-data chain.

## What MP-065 does not do

MP-065 **does not train a model**. It does not fit preprocessing statistics, calculate a physical model threshold, score validation/test records, diagnose a machine, estimate a failure probability, estimate RUL, publish physical measurements, or make a maintenance decision.

It opens no serial port, creates no Wi-Fi/network listener, adds no PLC or actuator/control path, and adds no remote deployment capability.

**MP-016 remains ON HOLD** for live sensors, edge/device transport, PLC integration, remote deployment, and machine-safety work. A future offline physical trainer must remain a separate reviewed milestone and must fail closed unless the exact MP-065 record, original decision, request, and upstream source chain all revalidate.
