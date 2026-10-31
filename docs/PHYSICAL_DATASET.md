# Local physical dataset cards and asset-disjoint splits (MP-059)

MP-059 turns verified MP-058 feature outputs into conservative **local-only** physical run cards and deterministic split plans. It exists to establish provenance and leakage boundaries **before** any physical-data modeling is considered.

This milestone **does not authorize training** or model scoring. Physical labels remain unknown, sensor calibration remains unverified, and failure evidence remains unknown by construction.

## Why the boundary is the whole physical asset

Repeated captures from the same motor are correlated: they share hardware, installation, sensor mounting, manufacturing tolerances, operating history, and often acquisition equipment. Splitting sessions or rows from one motor across train and test would create an optimistic leakage path even if timestamps differ.

MP-059 therefore groups by the **whole physical asset**. Every acquisition session and every derived feature row for one `asset_id` is assigned to exactly one of train, validation, or test. A motor cannot appear in more than one partition.

This split is label-blind. It does not inspect or infer machine-health truth when assigning assets.

## Physical run card

Create a run card from one MP-058 feature JSONL/report pair:

```bash
python -m motorpulse.physical_dataset card \
  --features physical-features.jsonl \
  --report physical-features-report.json \
  --session-id lab-session-001 \
  --out physical-run-card.json
```

A v1 card is bound to the deterministic MP-058 feature SHA-256 and preserves:

- one physical `asset_id`;
- one capture `device_id`;
- a user-assigned local `session_id`;
- first/last UTC capture timestamps;
- extracted and abstained row counts;
- sampling contracts observed in the session;
- sensor/firmware provenance;
- MP-058 feature SHA-256;
- canonical MP-057 frame SHA-256; and
- raw input-capture SHA-256 from the MP-058 report.

Cards intentionally contain no local absolute path and no raw acceleration waveform.

One run card must represent exactly one physical asset and one device-provenance contract. If firmware/sensor provenance changes, create a separate acquisition session/card rather than silently combining incompatible provenance.

## Truth, calibration, and rights status

MP-059 deliberately permits only these v1 states:

- `calibration_status = "unverified"`;
- `label_status = "unknown"`;
- `failure_evidence_status = "unknown"`;
- `publication_status = "local_only_do_not_redistribute"`;
- `redistribution_cleared = false`;
- `training_authorized = false`;
- `model_scoring_authorized = false`;
- `diagnosis_authorized = false`; and
- `rul_authorized = false`.

Editing a card to claim reviewed calibration, known fault truth, observed failure evidence, redistribution clearance, training authorization, diagnosis, or RUL makes the card invalid. A future evidence-review milestone must define how any of those states can be promoted safely and what independent evidence is required.

The project does not commit user physical measurements or MP-058 derived feature rows. A local run card is provenance metadata, not a redistribution license. Keep original captures, derived physical features, and cards private/local unless a separate source/ownership/privacy review explicitly authorizes publication.

## Whole-asset split plan

At least three distinct physical assets are required so train, validation, and test each contain an independent motor. Multiple sessions for the same asset are allowed and are grouped together.

```bash
python -m motorpulse.physical_dataset split \
  --card motor-a-session-1.json \
  --card motor-a-session-2.json \
  --card motor-b-session-1.json \
  --card motor-c-session-1.json \
  --out physical-split.json \
  --seed 42
```

The default asset-count ratios are 60% train, 20% validation, and 20% test. Ratios allocate **whole independent assets**, not rows or sessions. With small datasets the exact row percentages will therefore differ from the requested ratios.

The splitter rejects:

- fewer than three distinct assets;
- duplicate run-card identities;
- duplicate acquisition session identities;
- duplicate physical feature content reused across sessions;
- cards with modified canonical IDs;
- cards that promote calibration/labels/failure evidence; and
- cards that authorize redistribution, training, scoring, diagnosis, or RUL.

The resulting plan records local asset/session/card identities and feature hashes, is deterministic for the same seed/cards, and is independent of input-file ordering.

## Future model gate

A split plan is a **research design artifact**, not permission to fit a model. Before physical training can be enabled, a separate reviewed milestone must define at minimum:

1. sensor calibration and transfer-function evidence;
2. trustworthy machine-state/failure labels or a clearly defined unsupervised objective;
3. ownership/privacy/redistribution review for the physical dataset;
4. preprocessing fit only on training assets;
5. model/threshold selection without test-asset leakage;
6. held-out evaluation on physically independent test assets;
7. uncertainty, operating-domain, failure-mode, and claim review; and
8. explicit separation between research results and maintenance/safety decisions.

Synthetic MotorPulse metrics remain synthetic-only and cannot be reused as physical test performance.

## Hardware and safety boundary

MP-059 is file-based and offline. It opens no serial port, exposes no device/network listener, adds **no PLC** or actuator integration, and adds no remote deployment capability. It provides no diagnosis, maintenance command, failure probability, or **no RUL** estimate.

MP-016 remains the separate ON-HOLD milestone for actual live sensors, edge/device transport, PLC integration, and remote deployment. Those capabilities require dedicated security and machine-safety engineering rather than reusing the local research API.
