# MotorPulse AI — Simulation model, units and limitations (MP-026)

**Status:** Educational, deterministic, **synthetic** motor-condition-monitoring lab; not a physical motor digital twin, a validated fault classifier, an industrial sensor system or a predictive-maintenance product. This page is the authoritative technical reference for the assumptions implemented by the code as of MP-025. See [ARCHITECTURE.md](ARCHITECTURE.md) for software components and [TELEMETRY.md](TELEMETRY.md) for output fields.

> **Never use the dashboard, fault categories, health colors or thresholds for decisions about real machinery.** The model does not estimate a probability of failure, remaining useful life (RUL), or time to maintenance. Its fault scenarios are controllable labels for software experiments, not observations of actual damage.

## 1. Source-of-truth map

| Concern | Implemented in | Relevant documentation |
|---|---|---|
| Shaft tones, synthetic impacts and noise | `motorpulse/signals.py` | [SIGNALS.md](SIGNALS.md) |
| Fault activation, severity curves and operating schedules | `motorpulse/scenarios.py` | [SCENARIOS.md](SCENARIOS.md), [PROGRESSION.md](PROGRESSION.md) |
| RPM, temperature, waveform perturbations, features, rules, rolling samples | `motorpulse/sim.py` | [OPERATIONS.md](OPERATIONS.md) |
| Frequency-domain estimator | `motorpulse/spectral.py` | [SPECTRAL.md](SPECTRAL.md) |
| Schema, field types, unit declarations | `motorpulse/schema.py`, `docs/snapshot.schema.json` | [TELEMETRY.md](TELEMETRY.md) |
| Simulation progression and snapshot semantics | `motorpulse/controller.py` | [SIMULATION_CONTROL.md](SIMULATION_CONTROL.md) |
| Local configuration | `motorpulse/config_file.py` | [CONFIG_FILE.md](CONFIG_FILE.md) |

If a coefficient or threshold changes, update the corresponding Python constant, the tests and this document in the **same pull request**. No number below is an ISO acceptance limit, vibration severity standard, OEM specification or experimentally fit physical constant.

## 2. Units and acquisition time

| Quantity | Meaning | Units | Implementation detail |
|---|---|---|---|
| `rpm` | Rotational speed | revolutions/minute | Example speed is near 1480 RPM |
| `shaft_frequency_hz` | Shaft fundamental, `rpm/60` | Hz | Floating-point estimate |
| Raw waveform `a[i]` | Synthetic vibration acceleration | **g** (standard gravity acceleration) | **Not grams of mass** and not velocity in mm/s |
| `rms_g`, `peak_to_peak_g` | Acceleration signal summary | g RMS, g peak-to-peak | Calculated from 1024 samples |
| `crest_factor` | Peak absolute acceleration divided by RMS | dimensionless | Zero for an all-zero waveform |
| `temperature_c` | Synthetic asset temperature | °C | No thermal time constant or heat-transfer calculation |
| `shaft_1x_amplitude_g`, `shaft_2x_amplitude_g` | Hann-windowed harmonic estimate | g **peak** | Not RMS and not PSD |
| `band_80_400_rms_g` | Integrated Hann-windowed acceleration power | g **RMS** | Band is inclusive of 80 and 400 Hz |
| `rolling_rms_mean_g` | Arithmetic mean of latest available per-window RMS values | g | **Not** RMS of concatenated samples |
| `rolling_temperature_mean_c` | Arithmetic mean of tick temperatures | °C | Independent of vibration missingness |
| `step_seconds` | Virtual timestamp spacing | simulated seconds/tick | Default 1.5 s |
| `interval_seconds` | Background-worker scheduling interval | wall-clock seconds/tick | Default 1.5 s; not data acquisition time |

One sample window is `N = 1024` samples at `fs = 1024 Hz`: the nominal window duration is `N/fs = 1.0 s`, sample times are `i/fs` for `i=0...1023`, frequency-bin spacing is 1 Hz and Nyquist frequency is 512 Hz. The timestamp is the **start** of the virtual acquisition window. Tick 1 occurs at the configured `start_time_utc` (default 2026-01-01T00:00:00+00:00), and tick `k` has UTC timestamp `start + (k−1)·step_seconds`.

**Important:** virtual tick spacing is independent of the 1.0-second waveform window. A spacing greater than 1 second implies gaps; less than 1 second implies nominally overlapping windows. Noise and phase are regenerated for each tick, so there is **no continuous underlying physical waveform** even when timestamps suggest overlap. Polling `GET /api/snapshot` does not advance either clock.

## 3. Configured scenarios and fault severity

Valid synthetic machine-truth scenarios are `healthy`, `imbalance`, `bearing_wear`, `misalignment`, `overload`. A non-healthy scenario's strength `s` lies in [0,1]; this is an **arbitrary control parameter**, not physical damage fraction or failure probability. At strength zero, the effective waveform/scenario is healthy even if the configured fault is scheduled.

- `onset_tick = o` starts a scheduled fault inclusively; optional `duration_ticks = d` ends it at `o+d` exclusively.
- Constant progression uses target strength `s1` during the entire active interval.
- Linear and exponential progression interpolate from `s0` to `s1` over `r >= 2` ticks, attaining the target on `o+r−1`:
  - `p = (tick−o)/(r−1)`, clamped within the active ramp.
  - Linear: `s = s0 + (s1−s0)·p`.
  - Exponential: `s = s0 + (s1−s0)·expm1(4p)/expm1(4)`.
- The dimensionless exponential coefficient **4** is chosen only to produce an easily visible curve. After a duration ends, the waveform **immediately returns to healthy**, without lingering wear or residual damage.

Fault labels, configured target, active strength and progression phase are *simulator ground truth*. They must not be confused with the independent rule-based health output or the sensor-quality indicator.

## 4. RPM and illustrative operating load

For each motor and tick, the random generator is seeded by a reproducible combination of `seed`, `tick` and `asset_id`. Let `k = tick−1`. The example rotational speed and temperature begin as:

- `rpm_base = 1480 + Uniform(−24,24)` RPM.
- `T_base = 47 + Uniform(−3,3)` °C.
- `rpm = rpm_base · [1 + speed_variation_pct · sin(2πk/24)]`.
- `load_factor = 1 + load_variation_pct · sin(2πk/32 + 1)`.
- `T = T_base + 12·(load_factor−1) + ΔT_fault` °C.
- Entire acceleration samples after waveform generation are multiplied by `1 + 0.6·(load_factor−1)` when load variation is configured.

Both speed and load modulation occur **between ticks only**, not continuously within the 1.0-second waveform; they are deterministic sine fixtures. The load factor is dimensionless and **not** calibrated torque, shaft power, current, or mechanical work. Values cannot be converted to real operational duty or load.

The example fault temperature increments at active strength `s` are: imbalance `13s` °C, bearing wear `35s` °C, misalignment `9s` °C, overload `50s` °C, and healthy zero. No dynamics or thermal inertia connects temperature across ticks.

## 5. Synthetic acceleration formula

Let `f_s = rpm/60` Hz and `t_i = i/1024` seconds. The nominal synthetic acceleration before load, drift and outlier injection is:

```text
a(t) = A1(s)·sin(2π·f_s·t)
     + A2(s)·sin(4π·f_s·t + 0.35)
     + bearing_pulse(t, s)
     + Gaussian(0, sensor_noise_g)
```

For either harmonic, interpolate `A_j(s) = A_j(healthy) + s·[A_j(fault)−A_j(healthy)]`. These are **peak acceleration** amplitudes:

| Scenario | 1× target (g peak) | 2× target (g peak) | Thermal increment at strength 1 |
|---|---:|---:|---:|
| healthy | 0.12 | 0.015 | 0 °C |
| imbalance | 0.62 | 0.020 | 13 °C |
| bearing_wear | 0.22 | 0.025 | 35 °C |
| misalignment | 0.14 | 0.28 | 9 °C |
| overload | 0.20 | 0.025 | 50 °C |

Only `bearing_wear` adds the following positive pulse at active strength `s`:

```text
phase = (4.8·f_s·t) mod 1
distance = min(phase, 1−phase)
bearing_pulse = s·exp(−0.5·(distance/0.085)^2)    [g]
```

The **4.8×** impact rate, **0.085** cycle width and one-g full-severity pulse height are invented demonstration coefficients, not bearing geometry calculations. Specifically **4.8× is not a measured or calculated BPFO/BPFI/BSF/FTF**. Multiple pulse harmonics can exceed Nyquist, and the simulator has **no analog anti-alias filter**, sensor transfer function, resonance or calibrated mounting direction.

## 6. Sensor faults, missing data and provenance

- `sensor_noise_g` defaults to **0.014 g** Gaussian standard deviation. Noise is generated afresh with each seeded tick, not measured.
- `sensor_drift_g_per_tick` adds a DC offset of `clip((tick−1)·rate, −0.5, 0.5)` g to all 1024 samples. This is not a temperature compensation model.
- A configured outlier adds `sensor_outlier_g` to **one sample** at index `1024//3` on each scheduled tick. The injected outlier is known because the simulator scheduled it, **not** because a sensor-fault detector has discovered it.
- A missing-vibration interval takes precedence if it overlaps a scheduled outlier. The model still emits RPM and temperature; vibration features are **JSON null**, not zero, and the output is labeled `sensor_quality="missing"` and `health="unavailable"`.
- During an outlier interval, vibration features remain numeric but `sensor_quality="outlier"` and `health="suspect"`. Normal motor assessment is intentionally suppressed.
- With `sensor_quality="good"`, existing demo rules yield `normal`, `warning`, or `critical`. A 'good' sensor-quality flag means *no problem was injected*; it is **not evidence of calibrated sensor quality**.

Rolling vibration summaries use only nonmissing records among the last 5 generated ticks. At the **current missing tick**, `rolling_rms_mean_g` is null even if older valid observations exist, and `rolling_valid_observations` reports how many valid measurements remain in that 5-tick history. Rolling temperature remains available. Outlier values remain in the rolling vibration history and can contaminate subsequent readings; do not interpret that rolling mean as a robust statistic.

## 7. Feature calculations and rule-based health

For `N` waveform samples in g:

- `RMS = sqrt((1/N)·Σ a[i]^2)` (g RMS).
- `peak_to_peak = max(a)−min(a)` (g peak-to-peak).
- `crest_factor = max(|a|)/RMS` (unitless; 0 if RMS is zero).
- Frequency features are computed **after mean removal**, using a periodic Hann taper `w[i] = 0.5−0.5cos(2πi/N)` and a one-sided radix-2 FFT.
- Harmonic peak acceleration estimates use the largest FFT bin near the RPM-related 1× or 2× frequency, normalized by `2/Σw`.
- Power per bin is proportional to `factor·|FFT|²/(N·Σw²)` with factor 2 for positive interior bins and 1 at DC/Nyquist. The 80–400 Hz RMS is the square root of summed one-sided band powers. **This is not a power spectral density** (g²/Hz).

Hann windows mitigate leakage but also broaden main lobes. Off-bin tones are not amplitude-perfect; changes in waveform RPM, sensor drift and outliers may alter features for reasons unrelated to faults. There is no spectrum confidence interval or vibration velocity conversion.

The rule-based demo classifier in `motorpulse/sim.py` fires reasons for:

| Reason | Condition |
|---|---|
| Elevated vibration RMS | `rms_g >= 0.36` |
| High temperature | `temperature_c >= 82.0` |
| Impulsive waveform | `crest_factor >= 2.7 AND rms_g >= 0.20` |
| Critical health | At least one reason, AND (`rms_g >= 0.55 OR temperature_c >= 92.0`) |
| Warning health | One or more reasons, but critical condition not met |
| Normal health | No reasons on a valid, non-outlier measurement |

These numbers are **unvalidated demo thresholds**, not ISO 20816 vibration velocity criteria, manufacturer specifications, fitted decision boundaries, or trained model predictions. A synthetic fault can exist when `health="normal"`, and a change in simulated load/drift can trip a health rule **without a fault**.

## 8. Event semantics, reproducibility and API

- A snapshot has `schema_version="1.0.0"`, synthetic source, tick, virtual UTC timestamp and per-motor events; raw waveforms are **not** currently exposed.
- `event_id = sim:<seed>:<asset_id>:<tick>` is only unique within a run, **not globally unique** across reset or separate runs with the same seed.
- `GET /api/snapshot` and `GET /api/status` do not trigger simulation steps. `POST /api/control` handles start/pause/step/reset; `GET/PUT /api/config` reads/replaces scenarios (replacement pauses and resets to tick 1).
- Fixed seed, clock, motor configuration, and tick sequence produce repeatable telemetry **within the supported runtime**; byte-for-byte identity across different Python versions/platforms is not guaranteed without cross-environment testing.
- The server binds to `127.0.0.1` only and is not authenticated, production-hardened, or intended for network exposure.
- Telemetry v1 includes **nullable vibration fields** when sensor quality is missing. Applications must check `sensor_quality` and `health`; they must **not** coerce null to zero.
- The Python validator enforces additional cross-field constraints; the published JSON Schema does not model all of these conditional relationships. Treat both the schema and runtime checks as a contract for the synthetic lab, not an industrial data standard.

## 9. How to reproduce and check

From a clean checkout with Python 3.11+:

```bash
# Standard-library tests:
python -m unittest discover -s tests -v

# Default scenario; paused for deterministic inspection:
python -m motorpulse --paused

# Progressing faults, plus scheduled sensor outages:
python -m motorpulse --config docs/examples/operations-v1.json \
  --seed 42 --start-time-utc 2026-01-01T00:00:00Z --step-seconds 1.5 --paused

# In another terminal (while server is running):
curl http://127.0.0.1:8765/api/config
curl http://127.0.0.1:8765/api/snapshot
curl -X POST http://127.0.0.1:8765/api/control \
  -H 'Content-Type: application/json' -d '{"action":"step"}'
```

Each Step advances one virtual tick only while paused. Repeat the same setup and step count after Reset to inspect the same synthetic sequence. Check an event's `sensor_quality` before interpreting any vibration feature.

## 10. Known modeling gaps and future validation

1. **No real machine physics:** no bearing geometry, bearing characteristic frequencies, resonance, thermal inertia, load/torque calibration, rotational phase continuity, sensor placement/direction, field-measured noise, or validated degradation dynamics.
2. **No measurement-chain physics:** no ADC model, analog anti-alias filtering, sensor bandwidth/response, clock jitter, calibration drift diagnostics, or multiple sensor channels.
3. **No generalizable predictive model:** current health states are rule-based; there is no trained anomaly detector, failure probability, RUL estimate, calibration study, or uncertainty quantification.
4. **No durable histories or session identity:** rolling memory is bounded and in-process, while event IDs can repeat across runs.
5. **No external data validation:** synthetic examples are *not* the NASA IMS data. The IMS bearing datasets are separate real experimental resources requiring ingestion design, split-by-run/asset validation, provenance, and license/redistribution review.
6. **No industrial safety assurance:** no protection, electrical/functional safety controls, cybersecurity architecture, SCADA/PLC connectivity, maintenance work-order approval or production alerting.

**Next milestones:** MP-008 synthetic export and MP-027 IMS source-card research are complete. See [DATA_PROVENANCE.md](DATA_PROVENANCE.md) for the **unresolved** license/redistribution terms. MP-009 local-only IMS-style ingestion is implemented but has not been verified on real upstream files; MP-028+ nonleaky validation/evaluation, and MP-010/011 ML baselines and held-out reporting remain; do not publish original or derived IMS files until rights are clarified. Do not call a simulated fault label a model prediction.

## External methodological references

- [SciPy Hann window documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.windows.hann.html): window definitions and periodic vs symmetric convention; SciPy is **not a runtime dependency**.
- [SciPy periodogram](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.periodogram.html): one-sided frequency-domain normalization concepts.
- [NASA PCoE bearing-data repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/): separate experimental data for later benchmarking.
- [NASA Open Data — IMS Bearings](https://data.nasa.gov/dataset/ims-bearings): public dataset listing; **verify source terms before redistribution**.

These references justify background methods and future validation priorities, **not** our invented motor-fault amplitudes, bearing order, health thresholds, or temperature effects.
