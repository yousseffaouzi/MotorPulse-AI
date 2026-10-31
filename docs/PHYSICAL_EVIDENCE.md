# Physical calibration and evidence review protocol (MP-060)

MP-060 records **metadata about independently reviewed evidence** for a local MP-059 physical run card. It is a provenance/review layer only. It **does not authorize training**, physical model scoring, diagnosis, maintenance decisions, data redistribution, or deployment.

The protocol deliberately keeps three **independent categories**:

1. sensor/calibration evidence;
2. machine-state / failure evidence; and
3. rights/privacy evidence.

Reviewing one category does not imply anything about either of the other two.

## Why evidence is separate from the signal

Motor vibration, temperature, RPM, anomaly scores, threshold alarms, or other derived features are not acceptable ground truth merely because they look abnormal. **signal-derived inference is not evidence.** MP-060 therefore rejects `signal_inference` or model-output style origins for physical label/failure evidence.

A machine-state or failure claim must point to independent evidence such as an inspection, maintenance record, controlled test record, or observed failure record. The evidence metadata can say that such a record was reviewed; it does not embed the record or automatically make the dataset suitable for model training.

## Review request

A review request is local JSON with:

- `review_version = "1.0.0"`;
- a bounded local `reviewer_id`;
- an explicit `reviewed_at_utc` timestamp; and
- `calibration`, `label_failure`, and `rights_privacy` sections.

Each section has:

- `review_status`: `reviewed` or `not_reviewed`; and
- `evidence`: a list of evidence metadata records.

A `reviewed` category requires at least one evidence record. A `not_reviewed` category must have an empty evidence list, preventing hidden evidence from silently influencing a category.

Each evidence record contains only:

- `evidence_id`: a local stable reference chosen by the reviewer;
- `evidence_sha256`: SHA-256 of the evidence artifact or immutable exported record;
- `evidence_date_utc`;
- optional `expires_at_utc`;
- `origin`; and
- `kind`.

Private certificates, maintenance documents, ownership records, names, addresses, photos, or other sensitive evidence are **not copied into the repository by this protocol**. Keep those source documents in the appropriate private/local evidence store and record only non-sensitive references/hashes here.

## Allowed evidence classes

Calibration review accepts:

- `calibration_certificate`;
- `reference_instrument_record`; or
- `calibration_procedure_record`;

with origin `external_record` or `independent_measurement`.

Label/failure review accepts:

- `maintenance_record`;
- `inspection_record`;
- `controlled_test_record`; or
- `observed_failure_record`;

with origin `external_record`, `independent_observation`, or `controlled_test`.

Rights/privacy review accepts:

- `ownership_record`;
- `permission_record`;
- `consent_record`; or
- `privacy_review`;

with origin `external_record` or `owner_documentation`.

These allowlists are intentionally narrow. Adding a new evidence class is a contract change requiring code/test review.

## Deterministic time and expiry checks

The protocol does not use the computer's current wall clock. Evidence is evaluated against the explicit `reviewed_at_utc` in the request, making the review reproducible.

- Evidence cannot post-date the review.
- If `expires_at_utc` exists, it must be later than the evidence date.
- Expired evidence is rejected when `expires_at_utc <= reviewed_at_utc`.

This means a historical review can be reproduced exactly. A later operational decision about whether a historical review is still current is a separate policy question and must not silently rewrite the stored review.

## Source binding

The generated manifest records both:

- the MP-059 `run_card_id`; and
- SHA-256 of the canonical complete run card.

The review therefore cannot be reused on another acquisition session or on a modified card. Any change to the run card requires a new evidence review.

The manifest also has a deterministic `review_id` derived from its complete canonical content. Changing the reviewer, time, evidence ID/hash/date/origin/kind, category status, or run-card binding changes the review ID.

## CLI

```bash
python -m motorpulse.physical_evidence \
  --card physical-run-card.json \
  --request physical-evidence-review-request.json \
  --out physical-evidence-review.json
```

Input JSON is strict: duplicate keys, non-standard JSON constants, symlinks, oversized files, malformed hashes, invalid UTC timestamps, unsupported evidence kinds/origins, and inconsistent category states fail closed. Output is write-once and never overwrites an existing file.

## Authorization remains closed

Even when all three evidence categories are reviewed, MP-060 always writes:

- `publication_status = "local_only_do_not_redistribute"`;
- `redistribution_cleared = false`;
- `training_authorized = false`;
- `model_scoring_authorized = false`;
- `diagnosis_authorized = false`; and
- `rul_authorized = false`.

The manifest validator rejects attempts to flip any of those booleans. Evidence review is not authorization.

A future milestone may define a physical-training authorization process, but it must explicitly require appropriate evidence quality, leakage-resistant MP-059 splits, train-only preprocessing, held-out physical evaluation, and claim review. MP-060 itself provides **no RUL** or other prognostic capability.

## Hardware and safety boundary

MP-060 is offline and file-based. It opens no serial port, exposes no network/device listener, adds **no PLC** or actuator integration, and provides no remote deployment path.

MP-016 remains ON HOLD for live sensors, edge/device transport, PLC integration, and remote deployment. Those capabilities require dedicated transport security, device identity, replay protection, operational failure handling, and independent machine-safety engineering.
