# Physical final-test scoring (MP-072)

This local research command scores only the approved test partition using the
frozen MP-066 model and strict `score > threshold` comparison. No test result
exists unless the complete MP-071 record, exact MP-070 request, separately
supplied decision and all upstream sources revalidate. Unusable sensor rows
remain abstentions, with null scores and flags.

Scores are review-only standardized distances, not diagnoses, fault probabilities,
RUL predictions or maintenance recommendations. Counts of review flags are not
false-positive rates without independently verified labels.

## Source stability and scope

The command captures each feature file once into a private temporary directory
and verifies the captured canonical and raw byte digests against the bundle.
Every upstream replay and test calculation then uses those captured files.
Each copy is bounded by the existing feature-file size limit (256 MiB), with
a 1 GiB aggregate snapshot limit. Temporary copies are removed on ordinary
completion/error; a hard termination may leave files behind. Use a trusted
local machine and private temporary storage. This is not protection against
a hostile local operator or guaranteed secure erasure.

Full integrity replay reads all partitions and recomputes the prior train-only
fit and validation-only scores in memory. No new training or threshold selection
is performed; only test rows enter the new scoring operation. The source
artifacts remain unchanged. MP-076 shares the bounded snapshot mechanism with
training and validation operations and their replay validators. The test
partition is not cryptographically sealed.

The result binds the exact approval record, request, validation result, model,
split and bundle. It records row-level scores, abstentions, and counts without
raw sensor measurements or file paths. The validator recomputes the result.
Reviewer identity remains self-asserted and unsigned. Matching records are
not authentication or cryptographic proof of human consent.

## Local command

Use the MP-071 command's input arguments, replacing its module with
`motorpulse.physical_final_test_scorer` and adding
`--final-test-approval-record final-test-approval.json`.
Set `--out final-test-result.json`. The output is write-once; this does not
enforce a global one-shot evaluation ledger. Operators must not tune the model
or threshold based on test results or rerun a modified experiment on the same
holdout. Integrity replay of the identical frozen experiment is permitted.

All repository tests use synthetic physical-style fixtures and fixture-only
decisions. No real physical experiment is authorized by these tests. Inputs and
outputs remain local_only_do_not_redistribute. MP-016 remains ON HOLD.
