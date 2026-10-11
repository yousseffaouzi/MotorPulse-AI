# Telemetry contract (MP-006)

MotorPulse AI publishes an additive, **versioned snapshot JSON** contract. Current version: **1.0.0**. See [snapshot.schema.json](snapshot.schema.json) for JSON Schema Draft 2020-12 and [examples/snapshot-v1.json](examples/snapshot-v1.json) for a small validated example. Runtime validator: `motorpulse.schema.validate_snapshot` (Python standard library only).

## Snapshot and event fields

`/api/snapshot` returns `schema_version`, `source`, `tick` (starts at 1), `recorded_at_utc` and an `assets` list. Each asset is a **feature-summary event**, not a raw signal packet:

- Identity: `event_id` (currently `sim:<seed>:<asset_id>:<tick>`), `asset_id`, `name`, `source`, `scenario`.
- Time: `timestamp_utc` is the UTC measurement/snapshot timestamp. In v1 it equals `recorded_at_utc` for all assets in the same tick; it is presently wall-clock based, **not reproducible simulation time** (tracked as MP-018).
- Sampling: `sample_rate_hz` (currently **1024 Hz**), `sample_count` (currently **128**) describe the uniform simulated acceleration samples used to calculate features. The implied window duration is 0.125 s. Raw samples are **not returned** by the current endpoint. A physically realistic signal generator is still planned (MP-019).
- Units: `units.vibration_acceleration = "g"` (acceleration as multiples of standard gravity, **not** grams of mass); `units.temperature = "degC"`; `units.rotational_speed = "rpm"`.
- Measurements: `rpm` (revolutions/minute), `temperature_c` (degrees Celsius), `rms_g` and `peak_to_peak_g` (acceleration g), `crest_factor` (unitless).
- Rule output: `health` is `normal`, `warning` or `critical`; `reasons` lists the fired demo thresholds. **Not** a learned prediction or validated failure probability.

Event IDs are deterministic for a seed + asset + tick for reproducible lab examples. They are unique **within a snapshot**, but a new run with the same seed may reuse an ID. Durable globally unique run IDs are deferred to simulation session design (MP-018/MP-012); do not treat this as globally unique for cross-run database ingestion.

**Compatibility:** existing measurement field names and UI consumption are preserved. Future backwards-compatible fields may be added. Breaking shapes or changes in units require a new major `schema_version`. API consumers should check the major version and tolerate additional fields.

## Validation

```bash
python -m unittest discover -s tests -v
python - <<'PY'
import json
from motorpulse.schema import validate_snapshot
with open('docs/examples/snapshot-v1.json') as f:
    validate_snapshot(json.load(f))
print('telemetry v1 example valid')
PY
```

The built-in validator checks v1 required fields, finite numeric readings, positive sample metadata, canonical units, UTC offsets and uniqueness within the snapshot. JSON Schema consumers can use the published definition for structural validation; cross-field identity/time constraints require additional application validation.

## Limitations

The 64 Hz synthetic sine (`sample_rate_hz / 16`) is currently independent of motor RPM and is **not** calibrated to shaft-frequency harmonics, bearing geometry or measured industrial loads. Thresholds in `motorpulse/sim.py` are examples only. No dataset interchange/streaming or external-device schema is promised yet.
