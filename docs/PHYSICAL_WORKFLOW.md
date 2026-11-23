# Manifest-driven offline physical workflow (MP-074)

MP-074 provides one local command for each of four explicit stages:
train, validation, test, and report. It forwards inputs to the existing,
fully source-revalidating MP-066, MP-069, MP-072, and MP-073 entry points.

## Manifest

The manifest is strict JSON with these top-level fields:
workflow_manifest_version (1.0.0) and artifacts (an object).
Artifact names use underscores, not CLI dashes. File values are explicit local
paths, relative to the manifest's directory or absolute. Each of cards,
reviews, and features is a list of 3–1000 distinct paths.
No URLs, new labels, extra keys, or duplicated JSON object keys are accepted.

For example, a training-only manifest may contain:

~~~json
{
  "workflow_manifest_version": "1.0.0",
  "artifacts": {
    "training_approval_record": "training-approval-record.json",
    "training_request": "training-request.json",
    "training_decision": "training-decision.json",
    "preregistration": "preregistration.json",
    "bundle": "bundle.json",
    "readiness": "readiness.json",
    "split": "split.json",
    "cards": ["card-a.json", "card-b.json", "card-c.json"],
    "reviews": ["review-a.json", "review-b.json", "review-c.json"],
    "features": ["features-a.jsonl", "features-b.jsonl", "features-c.jsonl"],
    "protocol": "protocol.json"
  }
}
~~~

The files must actually exist and satisfy the original approval/source contracts.
A fixture decision used in tests is not real consent. Matching approval JSON
contains self-asserted, unauthenticated reviewer identity, not a signature.

## Commands

~~~text
python -m motorpulse.physical_workflow --manifest workflow.json --stage train --out physical-model.json
python -m motorpulse.physical_workflow --manifest workflow.json --stage validation --out validation-result.json
python -m motorpulse.physical_workflow --manifest workflow.json --stage test --out final-test-result.json
python -m motorpulse.physical_workflow --manifest workflow.json --stage report --out experiment-report.md --format markdown
~~~

Add the stage's additional artifact paths to the same manifest as they become
available. Validation additionally requires evaluation_approval_record,
evaluation_request, evaluation_decision and model. Final test also requires
final_test_approval_record, final_test_request, final_test_decision and
validation_result. Reporting also requires final_test_result.

Each invocation executes exactly one stage. It never creates or guesses
approval decisions, obtains permission from a generic 'continue', invokes a
later stage, overwrites a prior output, retunes a threshold, or accesses
ESP32/PLC/network/deployment hardware. The underlying implementation still
replays the exact entire upstream source chain (including parsing all cohort
feature files for integrity verification). No test values enter model fit or
validation scores. Test scoring requires its separate exact approval record.

Files and summaries remain local_only_do_not_redistribute. Write-once outputs
do not provide a global one-shot holdout ledger. This is a local convenience
layer, not authenticated authorization, field validation or an industrial
control application. MP-016 remains ON HOLD.
