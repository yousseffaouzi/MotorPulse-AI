# MP-019 — Synthetic acceleration waveform and spectral assumptions

MotorPulse AI is a **software-only teaching simulation**. Nothing here models actual motor bearings, sensor locations, bearing geometry, structural transfer functions, industrial vibration limits, maintenance probability, or Remaining Useful Life (RUL).

## Sampling model

- `sample_rate_hz = 1024` samples per second (uniform sampling)
- `sample_count = 1024` observations per event
- Nominal window duration `N / fs = 1.0 s` (the final sample is at 1023/1024 seconds)
- Nominal FFT bin spacing `fs / N = 1 Hz` (rectangular, one-second observation)
- Nyquist frequency `fs / 2 = 512 Hz`; modeled shaft and impulse repetition frequencies must be **strictly below** this limit.
- Acceleration values have units of multiples of standard gravity, `g` (not grams, not velocity in mm/s).
- The per-event `timestamp_utc` is the **virtual start** of its acquisition window, not the wall-clock time when the API is queried.
- `window_duration_s` and `shaft_frequency_hz` are optional additive fields in the telemetry v1 response (with `shaft_frequency_hz ≈ RPM/60`).
- Virtual clock `step_seconds` can differ from window duration. For `step_seconds < 1.0`, window time ranges overlap but sample noise and waveforms are regenerated independently; no continuous shaft phase or signal continuity is implied.

## Waveform equations

For equally spaced sample `i` at `t = i/fs`, define shaft frequency `f_s = RPM / 60` (Hz).

`a(t) = A1 · sin(2π f_s t) + A2 · sin(4π f_s t + 0.35) + n(t) + p(t)`

`n(t)` is repeatable pseudorandom Gaussian noise (standard deviation 0.014 g). The synthetic scenarios use these illustrative **peak acceleration** amplitudes:

| Scenario | A1 (1×) | A2 (2×) | Extra pulse | Available in 3-motor dashboard? |
|---|---:|---:|---|---|
| healthy | 0.12 g | 0.015 g | none | yes |
| imbalance | 0.62 g | 0.020 g | none | yes |
| bearing_wear | 0.22 g | 0.025 g | periodic smooth bumps at 4.8× | yes |
| misalignment | 0.14 g | 0.28 g | none | yes (MP-007) |
| overload | 0.20 g | 0.025 g | none | yes (MP-007; +50°C in thermal fixture) |

For `bearing_wear`, `p(t)` is a 1.0 g peak, smooth periodic Gaussian-shaped bump with repeating phase `(4.8 f_s t) mod 1` and relative phase width 0.085 cycles.

**IMPORTANT:** the value **4.8×** is an invented pedagogical choice, **not** a calculated BPFO/BPFI/BSF/FTF characteristic frequency. Real bearing frequencies depend on bearing geometry, speed and slip. This synthetic pulse shape includes harmonics above the nominal repetition rate and does **not** implement an analog anti-alias filter or sensor frequency response. Rejection of an undersampled **modeled repetition frequency** does not guarantee all pulse harmonics are alias-free. Do not use this simulator to diagnose machinery.

## Illustrative frequencies

At 1500 RPM: `f_s = 25 Hz`, 2× is `50 Hz`, and the illustrative 4.8× impact rate is `120 Hz`. Changing RPM to 1200 or 1800 moves 1× to 20 or 30 Hz respectively. The old frequency-independent 64 Hz sine has been removed.

The generator is deterministic for the same motor asset, seed, tick, and fault configuration. MP-007 interpolates 1×/2× amplitudes and illustrative bearing-pulse strength linearly from healthy (severity 0) to full synthetic fault (severity 1). It does not simulate progressive deterioration or maintenance-relevant severity thresholds. `motorpulse.signals.harmonic_amplitude_g()` provides a **single-frequency projection** for tests; it is not an FFT implementation. True Fourier spectra require suitable windowing, filtering, leakage accounting, sampling-time conventions and measured sensor calibration.

## Frequency-domain and temporal feature extraction

MP-023 provides additive spectral amplitude estimates, one-sided 80–400 Hz band RMS, and per-motor five-tick arithmetic rolling means. The frequency estimator uses a **periodic Hann window** and an O(N log N) pure-Python FFT. See [SPECTRAL.md](SPECTRAL.md) for windowing/leakage tradeoffs, g peak versus g RMS, and the distinction between rolling *mean of RMS features* and RMS over a concatenated waveform.

## Developer verification

```bash
python -m unittest discover -s tests -v
```

The regression suite checks 1× frequency tracking, increased 1× imbalance response, misalignment 2× fixture, synthetic bearing impulse repetition, spectral alias rejection, reproducibility, and consistency of telemetry units/window metadata. Normal/alert rule thresholds are still arbitrary demo values.

## Further reading

- Fluke: https://www.fluke.com/en/learn/blog/alignment/understanding-vibration-monitoring-common-faults-part-4
- Review of machinery vibration analysis: https://pmc.ncbi.nlm.nih.gov/articles/PMC10909639/
- Sampling theorem overview: https://www.sciencedirect.com/topics/engineering/sampling-theorem

These references inform the *qualitative* symptom patterns only; they do not validate our synthetic amplitudes or fault-severity thresholds.
