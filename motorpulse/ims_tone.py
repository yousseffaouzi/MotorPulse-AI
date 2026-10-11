"""Optional local native-rate, single-bin Hann amplitude on IMS-style records.

No resampling, bandpass/anti-aliasing claims, or conversion from input unit.
All input parsing is bounded. For illustrative research only.
"""
from __future__ import annotations

import hashlib
from math import cos, sin, pi, hypot, isfinite
from pathlib import Path
from typing import Any

from .ims import MAX_FILE_BYTES, MAX_LINE_BYTES, MAX_CHANNELS, MAX_SAMPLES, ALLOWED_UNITS, _local_timestamp, _positive_int


def native_hann_tone(path: str | Path, *,
                     sample_rate_hz: float,
                     expected_samples: int,
                     expected_channels: int,
                     requested_hz: float,
                     value_unit: str = "unknown") -> dict[str, Any]:
    """Estimate *peak* amplitudes at the nearest DFT bin using original fs.

    This is not a full spectrum or a bearing-defect-frequency estimator.
    Periodic Hann window and per-channel mean subtraction are applied before
    the single-bin DFT. No resampling is done, hence no digital anti-alias
    filter is claimed; acquisition-level aliasing remains unknown.
    """
    n = _positive_int(expected_samples, "expected_samples", MAX_SAMPLES)
    m = _positive_int(expected_channels, "expected_channels", MAX_CHANNELS)
    if n < 4:
        raise ValueError("a periodic Hann estimate requires at least 4 samples")
    for value, label in ((sample_rate_hz, "sample_rate_hz"), (requested_hz, "requested_hz")):
        if type(value) not in (float, int) or not isfinite(value) or value <= 0:
            raise ValueError(f"{label} must be finite and positive")
    if sample_rate_hz > 1_000_000 or requested_hz >= sample_rate_hz / 2:
        raise ValueError("frequency must be strictly below declared Nyquist")
    if value_unit not in ALLOWED_UNITS:
        raise ValueError("unverified unit; use unknown, g, m/s^2 or V")
    df = sample_rate_hz / n
    k = int(requested_hz / df + .5)
    if not 1 <= k < n / 2:
        raise ValueError("requested tone cannot be resolved from DC/Nyquist")
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("input must be a real local ASCII file, not a symlink")
    _local_timestamp(source.name)
    if not 0 < source.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("input exceeds raw-file size limit")
    re = [0.0]*m
    im = [0.0]*m
    totals = [0.0]*m
    window_re = 0.0
    window_im = 0.0
    window_sum = 0.0
    byte_count = 0
    sha = hashlib.sha256()
    with source.open("rb") as handle:
        for i in range(n):
            line = handle.readline(MAX_LINE_BYTES+1)
            if not line or len(line) > MAX_LINE_BYTES:
                raise ValueError("unexpected end of file or overlong line")
            byte_count += len(line)
            if byte_count > MAX_FILE_BYTES:
                raise ValueError("file too large")
            sha.update(line)
            try:
                columns = line.decode("ascii").split()
            except UnicodeDecodeError as exc:
                raise ValueError(f"row {i+1}: non-ASCII content") from exc
            if len(columns) != m:
                raise ValueError(f"row {i+1}: expected {m} channels")
            angle = 2*pi*k*i/n
            weight = .5 - .5*cos(2*pi*i/n)
            wr = weight*cos(angle)
            wi = -weight*sin(angle)
            window_sum += weight
            window_re += wr
            window_im += wi
            for j, token in enumerate(columns):
                try:
                    value = float(token)
                except ValueError as exc:
                    raise ValueError(f"row {i+1}: invalid numeric value") from exc
                if not isfinite(value):
                    raise ValueError(f"row {i+1}: nonfinite numeric value")
                totals[j] += value
                re[j] += value*wr
                im[j] += value*wi
                if not all(isfinite(x) for x in (totals[j],re[j],im[j])):
                    raise ValueError("numerical overflow")
        if handle.read(1):
            raise ValueError("file contains extra rows")
    amplitudes = []
    for j in range(m):
        mean = totals[j] / n
        amp = 2*hypot(re[j]-mean*window_re, im[j]-mean*window_im) / window_sum
        if not isfinite(amp):
            raise ValueError("nonfinite amplitude")
        amplitudes.append({"channel_id": f"ch-{j+1:02d}",
                           "peak_amplitude_native": amp})
    return {
        "source_filename": source.name, "source_sha256": sha.hexdigest(),
        "source_bytes": byte_count, "window": "periodic_hann",
        "sample_rate_hz_declared": float(sample_rate_hz),
        "sample_count": n, "frequency_bin_hz": df,
        "nyquist_hz_declared": sample_rate_hz/2,
        "requested_frequency_hz": float(requested_hz),
        "analyzed_frequency_hz": k*df,
        "value_unit": value_unit, "amplitudes": amplitudes,
        "resampling_applied": False,
        "aliasing_assessment": "unknown; upstream acquisition was not validated",
    }
