# Physical sensor gateway contract (MP-057)

MotorPulse AI now defines a **software-only capture contract** for a future ESP32 or similar edge device. This milestone does **not** connect to a serial port, Wi-Fi device, PLC, actuator, cloud service, or physical machine. It validates already-captured local JSONL files so firmware and host-side acquisition work can target a precise, reviewable format before any live hardware path is added.

The contract is intentionally separate from the synthetic `/api/snapshot` schema. Physical measurements must never be relabelled as synthetic faults, simulator health states, field diagnoses, failure probabilities, maintenance decisions, or RUL.

## Capture v1 frame

Each JSONL line is one `capture_version = "1.0.0"` frame with exactly these fields:

- `source`: fixed to `"physical_sensor"`.
- `device_id`: stable capture-device identity, for example an ESP32 board identity assigned by the lab.
- `asset_id`: stable physical test-asset identity. It is not a simulator motor ID unless the lab explicitly maps it.
- `sequence`: positive per-stream frame sequence number.
- `device_uptime_ms`: nonnegative monotonic device uptime in milliseconds.
- `captured_at_utc`: host/device measurement timestamp in UTC ISO 8601 form.
- `sample_rate_hz`, `sample_count`: acceleration acquisition sampling contract.
- `units`: exactly `g`, `degC`, and `rpm` using the canonical MotorPulse names.
- `quality`: independent `vibration`, `temperature`, and `rpm` states: `good`, `missing`, or `outlier`.
- `acceleration_g`: raw acceleration samples in g, or `null` when vibration quality is `missing`.
- `temperature_c`: temperature in degrees Celsius, or `null` when temperature quality is `missing`.
- `rpm`: nonnegative rotational speed, or `null` when RPM quality is `missing`.
- `provenance`: `device_family`, `firmware_version`, `accelerometer_model`, `temperature_sensor_model`, and `rpm_sensor_model`.

See [`examples/sensor-frame-v1.jsonl`](examples/sensor-frame-v1.jsonl) for a tiny structural example. Its values are illustrative test data, not measurements from a real motor.

## Validation

Validate a local capture without installing third-party dependencies:

```bash
python -m motorpulse.sensor_gateway docs/examples/sensor-frame-v1.jsonl
```

Or write a non-overwriting JSON validation report:

```bash
python -m motorpulse.sensor_gateway capture.jsonl --out-report capture-report.json
```

The validator rejects symlinked/missing files, blank or oversized frames, duplicate JSON keys, `NaN`/`Infinity`, unexpected v1 fields, unit mismatches, waveform-length mismatches, non-finite values, negative RPM, inconsistent missing-channel values, repeated/backwards sequence numbers, backwards device uptime, and non-increasing UTC timestamps.

Reports contain raw-file SHA-256 plus a canonical frame SHA-256. The canonical digest ignores JSON object-key order and insignificant whitespace, making it suitable for stable provenance comparisons. Reports intentionally omit local absolute paths.

## Current pipeline compatibility

The existing synthetic feature pipeline assumes a **1024 Hz, 1024-sample (1 second)** vibration window and good vibration/temperature/RPM channels. `current_pipeline_sampling_compatible()` reports whether a physical frame matches only those sampling and quality prerequisites.

That result is **not authorization to run the synthetic anomaly model on physical data**. MP-058 now implements offline, non-diagnostic feature extraction for compatible frames; see [PHYSICAL_FEATURES.md](PHYSICAL_FEATURES.md). Sensor calibration/transfer-function handling, asset-disjoint train/validation/test provenance, labeling/evidence policy, physical model training/scoring, and real-world evaluation remain separate future gates. Synthetic held-out metrics cannot be reused as physical performance evidence.

## Intended ESP32 path

A future hardware prototype can follow this staged path:

1. ESP32 samples an accelerometer and reads temperature/RPM sensors.
2. A host-side capture process adds/verifies UTC time and writes capture-v1 JSONL.
3. `motorpulse.sensor_gateway` validates provenance, ordering, channel quality, and file integrity offline.
4. `motorpulse.physical_features` converts compatible verified windows into provenance-bound, non-diagnostic feature rows and explicitly abstains on incompatible/poor-quality frames.
5. Only after dataset review and leakage-resistant splits may a physical-data model be trained/evaluated.
6. Live dashboard ingestion, device networking, PLC interaction, actuation, remote deployment, and maintenance decisions remain separate security/safety projects.

## Security and safety boundary

MP-057 and MP-058 add **no device listener and no control channel**. The main MotorPulse server remains localhost-only and unauthenticated because it is still a local research application. Do not port-forward it or connect physical control equipment to the current API.

Any future live device/network path requires a dedicated threat model, authenticated device identity, transport security, replay/ordering protection, rate/size limits, failure isolation, operational logging, and explicit review before implementation. Any PLC or actuator path additionally requires independent machine-safety engineering; it must not reuse the research dashboard control API as an industrial control interface.
