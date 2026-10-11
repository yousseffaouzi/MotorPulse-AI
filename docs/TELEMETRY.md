# Telemetry contract (MP-006)

MotorPulse AI publishes an additive, **versioned snapshot JSON** contract. Current version: **1.0.0**. See [snapshot.schema.json](snapshot.schema.json) for JSON Schema Draft 2020-12 and [examples/snapshot-v1.json](examples/snapshot-v1.json) for a small validated example. Runtime validator: `motorpulse.schema.validate_snapshot` (Python standard library only).

## Snapshot and event fields

`/api/snapshot` returns `schema_version`, `source`, `tick` (starts at 1), `recorded_at_utc` and an `assets` list. Each asset is a **feature-summary event**, not a raw signal packet:

- Identity: `event_id` (currently `sim:<seed>:<asset_id>:<tick>`), `asset_id`, `name`, `source`, `scenario`.
- Time: `timestamp_utc` is the UTC measurement/snapshot timestamp. In v1 it equals `recorded_at_utc` for all assets in the same tick. As of MP-018, these are deterministic **simulated UTC timestamps**: tick 1 is at `start_time_utc` and tick N at `start_time_utc + (N−1) × step_seconds`. They do not represent the real date/time of a HTTP request. See [SIMULATION_CONTROL.md](SIMULATION_CONTROL.md).
- Sampling: `sample_rate_hz` (**1024 Hz**), `sample_count` (**1024**) describe the uniform simulated acceleration samples used to calculate features. The window is **1.0 s**, the Nyquist limit is **512 Hz**, and the nominal DFT bin spacing is **1 Hz**. Optional additive fields `window_duration_s` (**1.0**) and `shaft_frequency_hz` (unrounded RPM/60, rounded for display) describe the model. Raw samples are **not returned** by the current API. See [SIGNALS.md](SIGNALS.md).
- Units: consult [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md) for the full sensor/feature unit table and their synthetic/non-calibrated meaning. `units.vibration_acceleration = "g"` (acceleration as multiples of standard gravity, **not** grams of mass); `units.temperature = "degC"`; `units.rotational_speed = "rpm"`.
- Measurements: `rpm` (revolutions/minute), `temperature_c` (degrees Celsius), `rms_g` and `peak_to_peak_g` (acceleration g), `crest_factor` (unitless).
- Spectral and rolling summaries (optional additive v1 fields since MP-023): `spectral_window`, `spectral_bin_hz`, `dominant_frequency_hz`, `shaft_1x_amplitude_g`, `shaft_2x_amplitude_g`, `band_80_400_rms_g`, `rolling_window_ticks`, `rolling_observations`, `rolling_rms_mean_g` and `rolling_temperature_mean_c`. See [SPECTRAL.md](SPECTRAL.md) for units and Hann FFT convention. These are not failure probabilities.
- MP-025 sensor provenance (optional additive v1 fields): `sensor_quality` is `good`, `missing` or `outlier`; `sensor_quality_reasons` describes the event. Missing vibration data uses JSON `null` and `health="unavailable"`; simulated outliers use `health="suspect"`. `load_factor`, `sensor_drift_g`, `operating_config`, and `rolling_valid_observations` preserve operating/sensor provenance. See [OPERATIONS.md](OPERATIONS.md).
- Rule output for good sensor readings: `health` is `normal`, `warning` or `critical`; `reasons` lists the fired demo thresholds. **Not** a learned prediction or validated failure probability.
- Progressive fault metadata (optional, additive v1 fields since MP-020): `progression` (constant, linear or exponential), `start_severity` (initial ramp strength), `ramp_ticks` (duration of ramp or null), `ramp_fraction` (0–1 normalized ramp position while active, not a failure probability), and `fault_phase` (healthy, scheduled, ramping, steady, ended). See [PROGRESSION.md](PROGRESSION.md).
- Scenario metadata (optional, additive v1 fields): `scenario` is the **effective** fault at this tick, `severity` its effective strength (0–1), `configured_scenario`, `configured_severity`, `onset_tick` and `duration_ticks` describe the scheduled fault. Outside its active tick interval readings revert to healthy (`severity=0`). See [SCENARIOS.md](SCENARIOS.md).

Event IDs are deterministic for a seed + asset + tick for reproducible lab examples. They are unique **within a snapshot**, but a new run with the same seed may reuse an ID. Durable globally unique run IDs are deferred to simulation session/storage design (MP-012); do not treat this as globally unique for cross-run database ingestion.

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

The built-in validator checks v1 required fields, finite nonmissing numeric readings, positive sample metadata, canonical units, UTC offsets, sensor-quality consistency and uniqueness within a snapshot. JSON Schema consumers can use the published definition for structural validation; cross-field identity/time constraints require additional application validation.

## Limitations

The synthetic base frequency now follows motor RPM / 60 (1×); a 2× component and optional illustrative 4.8× repeating bearing impulses are available. These models are **not** calibrated to real bearing geometry, sensor transfer functions, actual vibration velocity, or measured industrial loads. The generator does not implement anti-alias filtering for the pulse harmonics. Thresholds in `motorpulse/sim.py` are examples only. No dataset interchange/streaming or external-device schema is promised yet.
