# Offline physical feature extraction (MP-058)

MP-058 is the second hardware-readiness step after the MP-057 physical-sensor capture contract. It converts an already-captured, validated physical-sensor JSONL file into deterministic **measurement feature rows**. It does not score the synthetic anomaly model, does not apply the simulator's demo health rules, and does not train a model.

This is arithmetic feature extraction, **not field calibration** and not evidence that the current synthetic model transfers to a real motor.

## Input boundary

Input must satisfy [`SENSOR_GATEWAY.md`](SENSOR_GATEWAY.md): capture-v1 JSONL with explicit device/asset identity, sequence, device uptime, UTC timestamp, sampling metadata, canonical units, channel quality, raw acceleration, temperature, RPM, and sensor/firmware provenance.

Before extraction, the complete capture is validated by `motorpulse.sensor_gateway`. MP-058 then verifies that the same raw and canonical capture digests are still present while it reads the frames, so a file changed between validation and extraction is rejected.

## Feature-bearing frames

A frame is currently eligible for feature extraction only when:

- sampling is exactly **1024 Hz / 1024 samples**, matching the current one-second MotorPulse feature contract;
- vibration quality is `good`;
- temperature quality is `good`;
- RPM quality is `good`; and
- RPM is positive, because the current spectral summaries are shaft-referenced.

A stopped machine (`rpm = 0`) is a valid physical measurement, but this extractor explicitly abstains because 1×/2× shaft-referenced features are undefined under the current contract. It does not invent a small RPM or fake a frequency.

Missing, outlier, stopped, or incompatible-sampling frames remain in the output as `feature_status = "abstained"` with explicit reasons. Their derived vibration features are `null`. Measured temperature/RPM values and channel quality are retained when present so the abstention remains auditable.

## Extracted values

Eligible frames contain the same numerical feature definitions already used by MotorPulse research code:

- vibration RMS in acceleration g;
- vibration peak-to-peak in g;
- crest factor;
- Hann spectral bin width;
- dominant frequency;
- shaft 1× amplitude in g;
- shaft 2× amplitude in g;
- 80–400 Hz band RMS in g;
- measured temperature in degrees Celsius; and
- measured shaft speed in RPM.

The output intentionally does **not** contain the raw `acceleration_g` waveform. Every row includes `input_frame_sha256`, calculated from the canonical MP-057 input frame, plus the original device/asset/timing/sensor provenance.

## CLI

```bash
python -m motorpulse.physical_features capture.jsonl \
  --out-features physical-features.jsonl \
  --out-report physical-features-report.json
```

Both outputs are write-once. Existing files are never overwritten. The JSONL feature bytes are canonicalized for reproducibility; the report records the raw input SHA-256, canonical frame SHA-256, deterministic feature-output SHA-256, extracted/abstained counts, and explicit claim limits.

## What this does not authorize

The extractor produces measurements, not machine-health truth. Its output has no `health`, `scenario`, synthetic fault label, anomaly score, failure probability, diagnosis, maintenance recommendation, or RUL estimate.

The summary report explicitly records that:

- field calibration is false;
- training is not authorized by this step;
- model scoring is not authorized by this step;
- diagnosis is false;
- failure probability is false; and
- there is **no RUL** capability.

A future physical-data modeling milestone must separately establish sensor calibration/transfer-function handling, trustworthy labels or observational evidence, physically asset-disjoint train/validation/test splits, leakage controls, model selection, held-out evaluation, and claim review. Synthetic benchmark metrics cannot be relabelled as physical performance.

## Hardware and security boundary

**No serial** port is opened by MP-058, there is no Wi-Fi/network listener, there is **no PLC** or actuator integration, and there is no remote deployment path. The existing localhost research server remains separate from this offline processing step.

Actual ESP32 acquisition should first write MP-057 capture files through a separately reviewed host-side acquisition layer. Live ingestion, authenticated device transport, operational deployment, and any control-system integration remain later milestones with their own security and machine-safety requirements.
