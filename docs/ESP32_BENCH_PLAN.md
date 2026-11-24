# ESP32 bench acquisition design (MP-078)

**Design proposal — not approved for hardware operation.** This document
records a candidate architecture, not a wiring guide, purchase order,
firmware implementation, calibration certificate or safety assessment.
MP-016 remains ON HOLD. Independent lab review is required before physical
connection or acquisition. The repository has not collected real motor
measurements. Existing capture/feature tests use generated fixtures.

## Objective and boundaries

Demonstrate a measurement-only acquisition path on a supervised, guarded,
low-voltage motor bench. Separate motor power and independent safety
controls from the measurement system. The ESP32 must never command motor
motion, set speed, change load, drive an actuator or serve as an emergency
stop. Use a laboratory-approved enclosed rig with a manufacturer-supported
speed measurement interface; do not attach loose targets to rotating shafts
or improvise mains wiring. The lab supervisor must approve the specific
asset, mount, enclosure, power isolation and stop/disconnect procedure.
No purchase or energization is implied by this plan.

## Candidate bill of materials

| Candidate | Interface / function | Unresolved selection check |
|---|---|---|
| ESP32-S3 development board with exposed USB Serial/JTAG | Local USB; SPI acquisition and timestamping | Confirm exact board revision, pin allocation, logic levels, USB behavior and SDK version |
| ADXL355 evaluation board or documented breakout | Digital SPI accelerometer; data-ready/FIFO acquisition | Confirm usable range, mounting, selected axis, native clock accuracy, bandwidth and anti-alias response |
| TMP117 evaluation board or documented breakout | I2C contact temperature measurement | Confirm installed thermal path, electrical isolation, reference calibration and response time |
| Guarded low-voltage motor rig with integrated encoder/tachometer output | Read-only pulse measurement | Confirm pulses per revolution, electrical compatibility, safe speed range and independent tachometer |
| Local computer and suitable USB data cable | Record bounded local files; no public network | Confirm storage, UTC timebase, stable device identification and capture software |
| Lab-approved guarding, mounts, isolation, independent disconnect, reference accelerometer/shaker, thermometer and tachometer | Safety and metrology | Supervisor selects equipment; do not proceed without review |

Part numbers are candidate families, not an approved shopping list. No prices,
specific pin connections or motor supply ratings are assumed. Primary
manufacturer references (verify exact board revisions before implementation):

- [Espressif ESP32-S3 USB Serial/JTAG](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/usb-serial-jtag-console.html)
- [Analog Devices ADXL355 product information](https://www.analog.com/en/products/adxl355.html)
- [Analog Devices ADXL355 no-OS driver](https://developer.analog.com/docs/no-os/latest/drivers/accel/adxl355.html)
- [Texas Instruments TMP117 product information](https://www.ti.com/product/TMP117)

## Sampling decision: native rate is not 1024 Hz

The existing MP-058 feature extractor accepts 1024 Hz, 1024 samples and
good channels, and also requires positive RPM. Its feature band extends
to 400 Hz. ADXL355 nominal native ODRs include 1000, 2000 and 4000 Hz.
The manufacturer driver describes a 4000 Hz default with a 1000 Hz
low-pass corner. The proposed native acquisition uses 4000 Hz and 4000
samples for a nominal one-second window, subject to clock and filter
verification. Do not poll at 1024 Hz and pretend those readings are uniformly
sampled 1024 Hz data; do not pad/truncate a native window or rename its rate.

Phase A retains actual native capture-v1 files unchanged. At nominal 4000 Hz
they can pass the structural gateway but must abstain in MP-058. If timing,
range or quality is unknown, do not mark vibration good. Verify acquisition
with the sensor data-ready signal/FIFO, sample counts, reference timebase,
missed-sample detection and measured drift. Host arrival time is not sample
time. Never reconstruct missing samples as zero or duplicate a prior sample.

Phase B requires a separate, reviewed sampling/provenance design before any
1024 Hz feature-compatible data are produced. A candidate is a calibrated
anti-alias low-pass filter and rational conversion 4000 -> 1024 (32/125)
on a verified nominal timebase, with actual clock drift handled explicitly.
Preserve the 80–400 Hz band and attenuate signals above the 512 Hz output
Nyquist limit before downsampling. Filter continuously across windows or
explicitly discard/flag transients; verify passband gain, alias rejection,
group delay and timestamp alignment using reference tones. Keep original
native bytes, transformation settings/version and hashes. Capture v1 does
not have transformation provenance fields and describes raw measurements;
do not silently store resampled data as raw. A later reviewed schema/adapter
must bind that provenance, or the extractor must be deliberately extended
for native rates. Neither is implemented here.

Use a fixed signed acceleration axis and documented orientation/mount.
The current time-domain RMS includes DC; gravity, offset and mount transfer
function therefore matter. Do not silently substitute vector magnitude,
demean, filter or remove gravity without freezing and reviewing the
measurement contract. Temperature is measured at the mounted sensor location
(not motor winding temperature). RPM is estimated from validated pulse
counts/intervals and a verified pulses-per-revolution ratio, with documented
window timing, uncertainty and zero-speed policy.

## Proposed acquisition and host boundaries

```text
guarded rig -> read-only sensors -> ESP32 data-ready acquisition
           -> bounded local USB records -> private native capture-v1 JSONL
           -> existing offline gateway -> MP-058 (native-rate abstention)
           -> separate sampling/feature compatibility gate
           -> later separately authorized physical research experiment
```

The ESP32 buffers a bounded window, tracks a monotonic clock and sequence
number, and emits measurement records only. No motor command parser,
wireless listener, remote upload or control endpoint. Plan a separate
versioned device-to-host framing format with bounded lengths and checksum
for accidental corruption, distinguish diagnostics from records, and reject
corrupt or incomplete frames. USB checksums do not authenticate device
identity. No arbitrary serial commands or automatic reconnect after reset.
On overflow, disconnect, reboot or loss of timing, stop that session, keep
the partial evidence private and start a separately identified session only
after review. Document the actual USB interface and avoid mixing console
logs with capture records.

Host records an independent UTC anchor and the device monotonic window start,
with synchronization uncertainty and drift checks. Do not fabricate increasing
timestamps by adding an arbitrary millisecond. Reject or end a session on a
clock discontinuity or unbounded uncertainty. Use one device, one asset and
one provenance configuration per capture session; allocate the session ID
locally and bind it to the later run card. Retain a separate private acquisition
manifest with firmware/build hash, board and sensor identities, mount/axis,
ranges, native timing, synchronization uncertainty, calibration references,
pulse ratio, condition, start/end, gaps and stop reason; bind its hash and
the raw capture hash in the independent evidence chain before later research.
This sidecar is a proposed design, not currently enforced by MP-057.

## Capture-v1 mapping

Every JSONL line must contain exactly the existing [gateway contract](SENSOR_GATEWAY.md)
fields below. The host adds/verifies identity and UTC without changing the
observed waveform. No extra JSON keys are permitted.

| Field | Proposed producer / meaning |
|---|---|
| `capture_version` | Host: 1.0.0 |
| `source` | Host: physical_sensor (fixtures remain identified outside the data) |
| `device_id` | Reviewed stable local board ID |
| `asset_id` | Reviewed stable local motor ID |
| `sequence` | Positive, strictly increasing per device/asset stream |
| `device_uptime_ms` | Monotonic window-start uptime; strictly increasing in the stream |
| `captured_at_utc` | UTC window-start estimate derived from verified clock mapping |
| `sample_rate_hz` | Verified nominal native rate, 4000 in the candidate design |
| `sample_count` | 4000 native sample positions per proposed window |
| `units` | vibration_acceleration:g, temperature:degC, rotational_speed:rpm |
| `quality` | Exactly vibration, temperature, rpm; good/missing/outlier |
| `acceleration_g` | Signed finite calibrated-axis values, or null when missing |
| `temperature_c` | Finite measured sensor temperature, or null when missing |
| `rpm` | Finite nonnegative measured RPM, or null when missing |
| `provenance` | device_family, firmware_version, accelerometer_model, temperature_sensor_model, rpm_sensor_model |

Missing channel => null; outlier => actual finite measurement(s) with the
correct length for vibration, never invented samples. A lost vibration
window is missing, not padded. A true stationary measurement may be 0 RPM
when independently established, but MP-058 abstains at zero speed. Unknown
RPM is missing, not zero. Sensor saturation is an outlier if a complete
finite waveform was retained; otherwise mark missing. Structural validation
does not establish measurement quality, calibration or actual human consent.

Use conservative pilot file limits of 300 windows and 16 MiB, whichever
comes first (rotate only at explicit session boundaries); hard gateway limits
are 10000 frames, 256 MiB per capture, 1 MiB per line and 65536 samples per
frame. Bound receive buffers before parsing; refuse overwrite and symlinked
destinations, use private local storage, finalize files before offline
validation and keep the SHA-256. No real captures, approvals or calibration
records belong in GitHub. Generated fixtures must remain explicitly
identified as fixtures and never enter a real cohort.

## Acceptance matrix and go/no-go

These are proposed research acceptance targets, not industrial standards or
verified capabilities. Review uncertainty limits and the test protocol with
the lab before execution. No hardware test has been run.

| Check | Proposed acceptance evidence |
|---|---|
| Safety and configuration | Independent documented approval of guarded bench, mount, isolation, limits and disconnect; no software motor-control path |
| Offline fixture transport | Valid frames accepted; malformed, oversized, duplicate, corrupt and truncated records fail closed; no invented samples or clocks |
| Native timing | 300 consecutive nominal one-second windows; no unreported gaps/overruns; reference timebase error target <= 0.1%; record actual timing and uncertainty |
| Acceleration | Independent static-axis and dynamic reference comparison; no clipping; proposed amplitude error <= 5% over 80–400 Hz on approved reference apparatus |
| Temperature | Compare installed sensor against independent reference at approved stable points; proposed difference <= 1 degC; record thermal lag |
| RPM | Compare with independent tachometer across approved steady speeds; proposed error <= 2% or 5 rpm, whichever is greater; verify pulse ratio and zero-speed policy |
| Resampling (later gate) | Offline reference-tone tests: passband magnitude error <= 5%, aliases at least 40 dB down for specified stopband tones; independently review transition band, drift and transients |
| Disconnect / reboot / overflow | Acquisition stops or records explicit gaps; no fabricated continuity or automatic motor actions |
| Privacy and integrity | Local native capture and manifest hashes; retained calibration/evidence references; no overwrite, no publication |
| Gateway and feature outcome | Native fixture validates and abstains; after separate compatibility review only, compatible good positive-RPM frames may yield features |

Bench acceptance is staged: (1) document/independent review, (2) fixture-only
transport and file tests in a separately scoped implementation, (3) supervised
measurement-only bench authorization, (4) calibration and native-rate capture
qualification, (5) separate compatibility design approval. Fail any gate:
stop and resolve it; do not advance automatically. On loose mounts, guard
issues, unexpected heat/noise/vibration, electrical fault, lost timing or
sensor integrity, the supervisor uses the independent approved stop procedure;
do not rely on MotorPulse software as a safety device.

Once an authorized capture has been finalized, the existing offline commands
can be used without connecting the dashboard:

```bash
python -m motorpulse.sensor_gateway capture.jsonl --out-report capture-report.json
python -m motorpulse.physical_features capture.jsonl --out-features features.jsonl --out-report features-report.json
```

The proposed native capture must abstain, so it cannot be used to fit the
current model. One motor is sufficient for acquisition feasibility only.
At least three distinct assets are structurally required for the current
[asset-disjoint split](PHYSICAL_DATASET.md); meaningful evaluation requires
a separately justified cohort and independent evidence/rights review.
[Evidence review](PHYSICAL_EVIDENCE.md) and explicit training, validation
and final-test decisions remain mandatory. There is no diagnosis, RUL,
failure probability, maintenance decision or industrial readiness claim.

## Review status

Pending independent hardware/safety and metrology review. Exact component
boards, electrical design, safe operating envelope, reference instruments,
capture format and software implementation are not approved. MP-078
documentation is a planning deliverable; a separate implementation issue
and explicit go/no-go decision are required. MP-016 remains ON HOLD.
