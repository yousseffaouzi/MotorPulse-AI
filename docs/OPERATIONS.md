# MP-025 — Operational variability and sensor-quality events

MotorPulse AI simulates *illustrative operating conditions and sensor faults*, separately from its synthetic motor-fault labels. This is not an empirically validated asset/sensor model and **must not be used for physical equipment diagnosis**.

Load the example from the repository root:

```bash
python -m motorpulse --config docs/examples/operations-v1.json --paused
```

Use **Step +1** in the dashboard to inspect when a simulated motor fault grows, a sensor drops out, or an outlier occurs. All such events are deterministic for a seed/configuration/tick sequence and reset identically.

## Per-motor configuration fields

These are optional additive fields of the existing `assets` JSON objects (for `PUT /api/config` and `--config FILE`). Existing configurations are unchanged without them.

| Configuration field | Default | Allowed | Effect |
|---|---:|---|---|
| `speed_variation_pct` | 0 | 0–0.2 | RPM multiplied by `1 + p·sin(2π(tick−1)/24)` |
| `load_variation_pct` | 0 | 0–0.3 | Load factor `1 + p·sin(2π(tick−1)/32 + 1)`; synthetic temperature delta and vibration gain |
| `sensor_noise_g` | 0.014 | 0–0.1 g | Gaussian waveform sample noise standard deviation |
| `sensor_drift_g_per_tick` | 0 | −0.001 to +0.001 g/tick | Additive DC acceleration offset `clip((tick−1)·rate, −0.5, +0.5)` g |
| `sensor_missing_onset_tick` | null | 1–100000 or null | First vibration-dropout tick |
| `sensor_missing_duration_ticks` | null | 1–100000 or null | Number of consecutive dropout ticks |
| `sensor_outlier_onset_tick` | null | 1–100000 or null | First sensor-outlier tick |
| `sensor_outlier_duration_ticks` | null | 1–100000 or null | Number of consecutive outlier ticks |
| `sensor_outlier_g` | 0 | 0–2 g | Additive impulse magnitude at sample index `sample_count//3` |

For a missing or outlier window, **both** an onset and duration must be supplied. An outlier window requires positive `sensor_outlier_g`; without an outlier window it must be zero. Tick windows include the onset tick and exclude onset + duration. A missing sample window takes precedence if scheduled to overlap an outlier.

All operating variation is *across* generated simulation ticks, not within a 1024-sample acquisition window; a real machine may vary speed continuously within a window. These sinusoids are fixed fixtures, not evidence-derived physical operating models. They differ from machine fault `severity` and `progression`; speed/load variability **does not change the configured fault class**. The approximate load model perturbs temperature by `12·(load_factor−1)` °C and acceleration by `1 + 0.6·(load_factor−1)`.

## Sensor quality vs machine health

Each new event adds `sensor_quality`: `good`, `missing`, or `outlier`, and `sensor_quality_reasons`.

- **Good:** the original explainable `health` rules continue to yield `normal`, `warning`, or `critical`.
- **Missing:** `health="unavailable"`. Vibration RMS, crest, spectral features and vibration rolling RMS return JSON **null**; they do **not** become zero/healthy. RPM and temperature remain available, with rolling temperature still defined. `rolling_valid_observations` counts nonmissing vibration events in the last five simulation ticks; `rolling_observations` counts ticks including gaps.
- **Outlier:** `health="suspect"`; synthetic sensor impulse is present in vibration features, but any machine-maintenance interpretation is **suppressed**, rather than misreporting the impulse as a motor defect.
- A missing/outlier label does **not** change `scenario`, `fault_phase`, or fault `severity`; these describe the underlying *simulated machine truth*.

`load_factor`, `sensor_drift_g` and `operating_config` expose simulation provenance. The live dashboard uses an em dash (—) for missing vibration, shows sensor quality, and retains hidden sensor-event schedules when the editor submits an updated configuration.

This is synthetic injection with complete ground truth, not a validated instrument-health estimator. Simple rule-based alerts are still uncalibrated and are not trained ML predictions.

## Compatibility, evaluation and limitations

- Runtime validator accepts v1 records *without* these new fields. When present, it checks sensor-quality states and allows `null` vibration features **only when** the sensor is missing. The JSON Schema retains version `1.0.0` with additive optional metadata and nullable vibration readings.
- Rolling vibration features deliberately exclude missing measurements and are null **at the missing tick itself**. Historical rolling observations are limited to 5 ticks and reset with the simulator.
- If drift or external load changes push the original rule thresholds, those reflect an **uncalibrated demo** and may not imply any actual machine deterioration. Distinguishing operating confounders is a future benchmarking topic.
- Sensor outliers are injected into **one waveform sample** per active tick. They may alias or distort FFT estimates and are not a detailed electronic noise model.
- The model has no industrial sensor calibration, physics-based load transfer, sensor clock jitter, actual missing waveform transport, real bearing defect frequencies, or trained fault diagnosis.

Run:

```bash
python -m unittest discover -s tests -p 'test_operations.py' -v
python -m unittest discover -s tests -v
```

For context on operating variability and fault-condition interpretation, see these reviews (the synthetic coefficients above are not sourced from them):

- [Critical challenges and advances in vibration signal processing for non-stationary condition monitoring](https://www.sciencedirect.com/science/article/pii/S1474034625001831), 2025.
- [A review on vibration-based condition monitoring of rotating machinery](https://www.mdpi.com/2076-3417/12/3/972), 2022.
