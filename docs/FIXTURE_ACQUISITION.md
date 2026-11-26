# MP-079 — Fixture-only acquisition packet experiment

This software-only experiment is independent of the pending MP-078 bench
review. It is not a hardware wire protocol, firmware, serial listener,
capture service, real-data authorization or transport security design.
MP-016 remains ON HOLD. It must not be used to connect physical equipment.

The experiment tests how generated native-rate capture-v1-shaped frames
survive bounded binary framing and strict parsing. Both asset and device
IDs must begin with `fixture-`. That marker is a convention, not proof of
origin. Do not use real measurements or insert fixtures into a physical
cohort. The module accepts only complete in-memory bytes and has no CLI,
device/file I/O or output writer.

## Packet contract (experimental)

| Field | Encoding |
|---|---|
| Magic/version | Four ASCII bytes MPF1, reserved for fixtures |
| Length | Unsigned 32-bit big-endian payload byte count |
| Checksum | Unsigned 32-bit big-endian CRC32 of payload |
| Payload | Canonical capture-v1 JSON bytes, UTF-8, no newline |

The payload is validated against MP-057, then checked for the proposed
4000 Hz / 4000-sample native shape. The gateway's missing and outlier
semantics are preserved; no samples or timestamps are invented.
The parser reserializes and compares canonical bytes, rejecting ambiguous
JSON or noncanonical encodings. CRC32 detects accidental corruption, not
malicious modification or authenticated device identity.

A batch contains 1–300 packets and at most 16 MiB including headers.
Payload length is at most 1 MiB minus one byte (room for the JSONL newline).
Reject empty, truncated, malformed, oversized, corrupt or trailing bytes.
Do not scan for new magic to recover after corruption. All frames in a batch
must have identical device, asset and provenance identities, contiguous
sequence numbers and strictly increasing uptime and UTC. A gap/reboot ends
this experimental batch; the parser does not repair, reconnect or combine
batches. There is no cross-batch replay protection or measured clock accuracy.

These are in-memory limits, not a bound on memory already allocated by
a caller or a live receive buffer. Python decoded objects can occupy more
memory than the encoded bytes. No trusted timebase, calibration, sensor
range or physical provenance is established by structural validation.

## Reproducible fixture checks

```bash
python -m unittest discover -s tests -p test_fixture_acquisition.py -v
```

The test suite generates native-rate frames, round-trips packet bytes,
and creates a temporary fixture-only JSONL to exercise MP-057 and MP-058.
The gateway accepts the native sampling metadata and the current extractor
abstains: 4000 Hz must not be relabelled as 1024 Hz. No feature contract,
model math, dataset authorization, dependency, or dashboard changed.

A later actual device protocol requires independent bench approval, a
separate implementation/review, bounded streaming, explicit boot/session
identity, time synchronization uncertainty, calibration and real acquisition
provenance. A separate compatibility gate must address native-rate features
or verified resampling without silently representing derived samples as raw.
