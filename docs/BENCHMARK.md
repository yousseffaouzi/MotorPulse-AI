# MotorPulse AI — Dated synthetic benchmark (MP-015)

**Benchmark date:** 2026-10-15

This is a **synthetic-only** reproducibility snapshot. It compares the frozen
healthy-trained anomaly baseline with the existing illustrative rules on
disjoint **whole-run** held-out generator runs. These numbers are **not field performance**.
They are not calibrated failure probability, physical maintenance lead time,
industrial reliability, or Remaining Useful Life (**RUL**) evidence.

![Synthetic benchmark demo card](demo/benchmark-summary.svg)

## Reproduce

Run the underlying experiment into a new directory:

```bash
python -m motorpulse.experiment \
  --config docs/examples/experiment-v1.json \
  --out-dir /tmp/motorpulse-mp015-experiment
```

Regenerate this report and its repo-local SVG media on Python 3.13:

```bash
python scripts/generate_benchmark_report.py \
  --date 2026-10-15 \
  --config docs/examples/experiment-v1.json \
  --markdown docs/BENCHMARK.md \
  --svg docs/demo/benchmark-summary.svg
```

The generator creates outputs exclusively and refuses to overwrite existing files.
For a byte-for-byte check, generate into new temporary paths; the Python 3.13
regression test does exactly that. Cross-Python floating-point byte identity is
not claimed by the project.

## Fixed benchmark setup

- Config: `docs/examples/experiment-v1.json`
- Generator seeds: `[11, 22, 33, 44, 55]`
- Ticks per run: 24
- Virtual step: 1.5 seconds
- Whole-run split ratios: `[0.6, 0.2, 0.2]`
- Training groups: `synthetic-run:8fd4e8c50ce5edc318f2a56d, synthetic-run:b64ebbbc6350f9a57b90a1ba, synthetic-run:e4cfdcc0e803338ea7d54b1e`
- Validation groups: `synthetic-run:a0068e286b16343def7b2c48`
- Test groups: `synthetic-run:faaa3d241f2e4513fe3216a7`
- Model fitting: healthy + sensor-good training windows only; preprocessing and
  the original anomaly threshold stay frozen for validation/test.
- Both model and rules use the same good-sensor held-out denominator; missing
  and injected-outlier windows are abstentions.

## Validation held-out

- Whole-run evaluated groups: `synthetic-run:a0068e286b16343def7b2c48`
- Eligible good-sensor windows: 68 / 72
- Sensor abstentions: `{"missing": 2, "outlier": 2}`
- Synthetic fault episodes: 1 total; model detected 1, missed 0; mean delay 0 simulated seconds

| Metric | Model | Rules |
| --- | ---: | ---: |
| Eligible windows | 68 | 68 |
| TP | 18 | 14 |
| FP | 1 | 0 |
| TN | 49 | 50 |
| FN | 0 | 4 |
| Precision | 0.947368 | 1 |
| Recall | 1 | 0.777778 |
| F1 | 0.972973 | 0.875 |
| FPR | 0.02 | 0 |
| PR average precision | 1 | undefined |
| False alarms / simulated negative hour | 48 | 0 |

Evaluation SHA-256: `534b685cf0943eb202108a1ba70bcd8fe4fbabe7783d511597e8d03e3a2c4815`

## Test held-out

- Whole-run evaluated groups: `synthetic-run:faaa3d241f2e4513fe3216a7`
- Eligible good-sensor windows: 68 / 72
- Sensor abstentions: `{"missing": 2, "outlier": 2}`
- Synthetic fault episodes: 1 total; model detected 1, missed 0; mean delay 0 simulated seconds

| Metric | Model | Rules |
| --- | ---: | ---: |
| Eligible windows | 68 | 68 |
| TP | 18 | 14 |
| FP | 0 | 0 |
| TN | 50 | 50 |
| FN | 0 | 4 |
| Precision | 1 | 1 |
| Recall | 1 | 0.777778 |
| F1 | 1 | 0.875 |
| FPR | 0 | 0 |
| PR average precision | 1 | undefined |
| False alarms / simulated negative hour | 0 | 0 |

Evaluation SHA-256: `aa1790df6cbd13230a276f1b8054e127a5a948ad698fe3c1106126ce4a342816`

## Provenance

- Experiment config SHA-256: `a5f456e4adc331571538080ce17dba178b39268cec742c78b04c5d9eda732ee5`
- Split plan SHA-256: `73f218fddf9c2c5d3f7c922fa0d62b1ec3d1beced8f4b2f937ceb137546c200f`
- Trained model SHA-256: `e8ff6f40e5b234de0dd17701ca287c8057699c10be78aff1131a98fe0fbbce60`
- Portable artifact SHA-256: `be67740217503e767b926c2494f21b5ab0a4139d17dac9da21d837c8dec045ad`
- Feature pipeline SHA-256: `755c7dab9157b2199327e4abcd02b2c831dbe92c95dd6ade30cfb23e352bb5ba`
- Runtime dependencies recorded by the experiment: none.
- Source data: locally generated MotorPulse synthetic feature events only; no
  IMS archive or third-party derived records are used.

## Interpretation limits

The benchmark is a software/reproducibility demonstration against scripted
simulator truth. Distinct seeds still share the same generator equations and do
not establish independent machine populations. A higher synthetic metric does
not validate diagnosis, alert calibration, domain transfer, maintenance value,
failure probability, or RUL. The SVG is generated from the same test report and
is demo media, not a screenshot of physical equipment or measured telemetry.
