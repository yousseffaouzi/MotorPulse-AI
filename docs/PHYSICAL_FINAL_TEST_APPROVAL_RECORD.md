# Physical final-test approval record (MP-071)

MP-071 derives a local approval record from an exact MP-070 pending request and
a separately authored human decision. It does not generate the human decision
or score test data. A generic instruction such as `continue` is not approval.

## Decision contract

Provide a JSON object containing exactly these keys:

- `final_test_approval_decision_version`: `1.0.0`
- `final_test_request_id`: exact MP-070 request ID
- `final_test_request_sha256`: canonical SHA-256 of the entire request
- `approval_challenge_sha256`: exact request challenge
- `decision`: `approve_final_test_scoring_only`
- `human_affirmation`: exact request approval phrase
- `reviewer_assertion`: explicit 1–128 character identifier
- `decided_at_utc`: valid UTC timestamp ending in Z

The reviewer identity is self-asserted and is not authenticated. The decision is
unsigned. A matching artifact is not cryptographic evidence of human consent;
the operator must establish identity and actual authorization independently.

## Scope

The exact original request, separately supplied decision, frozen validation result,
model and full source chain are required. The output is not a standalone bearer
token. Only `test_scoring_authorized = true` is newly granted. The output keeps
`test_scoring_completed = false` and `test_rows_consumed = 0` for scoring.
No new fit, recalibration, train/validation experiment, test scoring, publication,
diagnosis, failure probability, RUL, network, deployment or control is performed.

Full integrity replay reads all feature files and recomputes prior train-only
fitting and validation-only scores in memory. No test values enter those
calculations. The accepted artifacts remain unchanged; a truly sealed test
partition is not provided by this design.

## Local command

Use the MP-070 command's existing input arguments, replacing its command module
with `motorpulse.physical_final_test_approval_record`, adding
`--final-test-request final-test-request.json` and
`--final-test-decision final-test-decision.json`, and setting
`--out final-test-approval.json`. The output is write-once. The API validator
requires the same original request, decision and source chain.

All repository test decisions are synthetic fixtures, not real approval.
Artifacts remain `local_only_do_not_redistribute`. MP-016 remains ON HOLD.
