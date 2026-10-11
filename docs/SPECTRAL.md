# MP-023 — Spectral and tick-based rolling signal features

MotorPulse AI is a deterministic, **synthetic educational simulation**, not a calibrated accelerometer, diagnostic instrument or trained fault predictor. New measurements are **additive optional fields in v1 telemetry**; existing rules use the original RMS, temperature and crest factor and have not been retrained or recalibrated.

## Spectral processing

The generator uses N = 1024 acceleration samples per event at fs = 1024 Hz (a one-second window). The spectral estimator in \`motorpulse/spectral.py\` is a bounded, standard-library-only radix-2 Cooley–Tukey FFT. Input arrays must have power-of-two length 8–8192, finite real acceleration values, sample rate strictly above 800 Hz (so the 80–400 Hz band fits below Nyquist), and a 2× shaft frequency strictly below Nyquist.

1. Detrend by subtracting the sample mean.
2. Apply the **periodic Hann window** \`w[i] = 0.5 − 0.5 cos(2πi/N)\`.
3. FFT the windowed input, retaining bins \`k = 0 ... N/2\`; bin frequency is \`k·fs/N\`.
4. Compute a one-sided **mean-square power per bin**, \`p[k] = factor[k]·|X[k]|² / (N·Σw²)\`, where \`factor=2\` for non-DC/non-Nyquist bins, \`factor=1\` at DC/Nyquist. Units are **g² per bin**, not PSD units of g²/Hz.
5. \`band_80_400_rms_g = sqrt(Σ p[k])\` for bins from 80 through 400 Hz (inclusive); this is acceleration RMS in **g**, not velocity mm/s.
6. For 1× (RPM/60) and 2× shaft harmonics, report a **peak amplitude** estimate \`2|X[k]|/Σw\` at the strongest bin within roughly one bin of the target. These estimates are **g peak**, not RMS; Hann scalloping means off-bin values are underestimates.
7. \`dominant_frequency_hz\` is the center frequency of the strongest non-DC one-sided power bin; on an exactly constant signal it is 0.

Sampling gives nominal frequency resolution \`fs/N = 1 Hz\` for the default waveform. A window trades sidelobe suppression for wider main lobes. Because fault signatures can vary by RPM, a 1×/2× bin neighborhood is used rather than assuming exact integer frequencies. Strong fault impulses and noise can create spectral leakage or aliasing; this method is **not a calibrated bearing-frequency detector**.

**No NumPy/SciPy runtime dependency** was introduced. SciPy and NIST documentation are engineering references for our convention, not external runtime requirements:

- [SciPy periodogram: one-sided power, window and scaling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.periodogram.html)
- [SciPy Hann window: periodic versus symmetric](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.windows.hann.html)
- [NIST discussion of spectral leakage and windowing](https://tf.nist.gov/phase/Properties/ten.htm)

## Rolling feature contract

Each generated **simulation step**, not each HTTP request, appends the event's computed RMS acceleration and temperature to a **separate per-asset in-memory history** of up to 5 ticks. New telemetry includes:

| Field | Unit | Definition |
|---|---|---|
| \`spectral_window\` | none | \`"hann"\` |
| \`spectral_bin_hz\` | Hz | fs/N |
| \`dominant_frequency_hz\` | Hz | strongest non-DC spectrum bin center |
| \`shaft_1x_amplitude_g\` | g peak | 1× shaft spectral peak amplitude estimate |
| \`shaft_2x_amplitude_g\` | g peak | 2× shaft spectral peak amplitude estimate |
| \`band_80_400_rms_g\` | g RMS | windowed one-sided integrated band energy |
| \`rolling_window_ticks\` | ticks | fixed capacity, currently 5 |
| \`rolling_observations\` | events | number of observed ticks, 1–5 |
| \`rolling_rms_mean_g\` | g | arithmetic mean of *previously computed* per-window RMS values |
| \`rolling_temperature_mean_c\` | °C | arithmetic mean of per-window temperatures |

The rolling RMS **mean** is deliberately **not** the physical RMS of concatenated raw acceleration windows; the name avoids conflating the two.

GET \`/api/snapshot\` is read-only. Snapshot polls do not append history. A reset or accepted new config constructs a fresh simulator and therefore resets the rollup; an identical seed/configuration/tick sequence reproduces the same spectral and rolling metrics.

## Scope and validation

\`\`\`bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p 'test_spectral.py' -v
\`\`\`

The dedicated tests include numerical tones at 25/50/120 Hz, a direct eight-point DFT reference, expected acceleration-band RMS, off-bin frequency tolerance, nonfinite and aliasing guardrails, relative scenario signatures, 5-tick rollups, snapshot purity, and deterministic replay.

The UI displays 1×/2× amplitudes, 80–400 Hz band RMS and a 5-tick rolling RMS mean. **No historical database**, production signal analyzer, PSD exporter, calibrated thresholds, fault probability, or Remaining Useful Life model is included in this milestone; those remain separate roadmap tasks.
