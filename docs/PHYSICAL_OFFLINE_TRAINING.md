# Physical offline training (MP-066)

MP-066 adds the first trainer that may fit a model from local physical feature
rows. It is intentionally narrow: training is permitted only after the **complete
MP-065 approval chain** revalidates against the exact MP-064 request, separate
human-decision artifact, MP-063 preregistration and protocol, MP-062 bundle,
MP-061 readiness assessment, MP-059 split, run cards, evidence reviews, and the
exact MP-058 feature-file bytes.

A copied approval record is not sufficient. The trainer revalidates all of those
sources before it reads rows for fitting.

## What MP-066 fits

The only supported model family is
`standardized_distance_baseline_v1`, exactly as frozen by MP-063.

The fit uses the **train partition only**:

- preprocessing center and population standard deviation are derived only from
  extracted train rows;
- zero/near-zero scales use a deterministic positive scale floor;
- the standardized-distance baseline is fitted only from those same train rows;
- the empirical threshold is derived only from train scores at the exact
  preregistered quantile;
- abstained rows are excluded from fitting;
- required feature values must be finite and nonnegative;
- the input allowlist is exactly `rms_g`, `crest_factor`,
  `band_80_400_rms_g`, `temperature_c`, and `rpm`;
- the current physical feature contract remains 1024 Hz / 1024 samples with
  good vibration, temperature, and RPM quality.

The validation and test are untouched: MP-066 does not fit on them, calibrate on
them, or score them.

## What the model artifact means

A successful artifact records that the exact approved offline training operation
completed. It contains fitted centers, population deviations, effective scales,
the train-only threshold, and source/approval hashes needed to reproduce and
revalidate the operation.

The artifact remains local physical-data-derived material with
`publication_status = local_only_do_not_redistribute`.

The following boundaries remain false:

- `model_scoring_authorized = false`
- `diagnosis_authorized = false`
- `failure_probability_authorized = false`
- `rul_authorized = false`
- `deployment_authorized = false`
- `redistribution_cleared = false`

The standardized-distance output is an anomaly-distance construction. It is
**not a failure probability**, diagnosis, maintenance recommendation, or RUL
estimate.

MP-066 does not score any physical row. A later milestone would need a separate,
reviewed scoring boundary and must revalidate the trained artifact and its
sources.

## Human-approval and fixture boundary

MP-066 does not create, infer, or repair human approval. It accepts only the
separate decision already required by MP-065 and revalidates that decision
against the exact MP-064 challenge and full upstream source chain.

Repository tests use synthetic physical-style fixtures. Their fixture decisions
are non-operational and authorize no real dataset, device, person, or deployment.
A generic message such as `continue`, a green CI run, or generation of a request
does not become approval.

## Offline CLI

The module is intentionally invoked directly so it is not confused with the
existing synthetic training commands:

```bash
python -m motorpulse.physical_offline_trainer \
  --approval-record approval-record.json \
  --request approval-request.json \
  --decision human-decision.json \
  --preregistration preregistration.json \
  --bundle bundle.json \
  --readiness readiness.json \
  --split split.json \
  --card run-card-train.json \
  --card run-card-validation.json \
  --card run-card-test.json \
  --review evidence-train.json \
  --review evidence-validation.json \
  --review evidence-test.json \
  --feature features-train.jsonl \
  --feature features-validation.jsonl \
  --feature features-test.jsonl \
  --protocol protocol.json \
  --out physical-model.json
```

The command is offline, standard-library only, and write-once. It opens no serial,
Wi-Fi, HTTP listener, PLC, actuator, or remote-control connection. It refuses to
overwrite an existing model file.

## Hardware boundary

MP-066 changes no hardware-control boundary. It adds no ESP32 connection,
automatic acquisition, PLC/actuator path, remote deployment, or autonomous
maintenance action. **MP-016 remains ON HOLD**.
