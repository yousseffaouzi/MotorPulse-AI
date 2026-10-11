"""Bounded dependency-free FFT features for synthetic acceleration data.

Hann-windowed, mean-detrended, one-sided spectrum at nonnegative frequency
bins. Values are illustrative, not calibrated for field diagnostics.
"""
from __future__ import annotations

from math import cos, isfinite, pi, sin, sqrt

MAX_FFT_SAMPLES = 8192
ROLLING_WINDOW_TICKS = 5
BAND_LOW_HZ = 80.0
BAND_HIGH_HZ = 400.0


def _fft_radix2(values: list[complex]) -> list[complex]:
    """Cooley-Tukey radix-2 FFT, standard library only, O(N log N)."""
    result = values.copy()
    n = len(result)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            result[i], result[j] = result[j], result[i]
    span = 2
    while span <= n:
        half = span // 2
        omega = complex(cos(-2 * pi / span), sin(-2 * pi / span))
        for offset in range(0, n, span):
            phase = 1 + 0j
            for k in range(half):
                u = result[offset + k]
                v = phase * result[offset + k + half]
                result[offset + k] = u + v
                result[offset + k + half] = u - v
                phase *= omega
        span *= 2
    return result


def spectral_features(samples: list[float], rpm: float,
                      sample_rate_hz: int = 1024) -> dict[str, float | str]:
    """Return Hann FFT amplitude and energy summaries.

    1x/2x amplitude estimates use the strongest bin within +/- 1 bin of
    RPM/60 and 2*RPM/60. Off-bin tones exhibit scalloping/leakage.

    Band RMS is sqrt(sum(one-sided Hann-windowed mean-square power per bin))
    over 80 <= f <= 400 Hz; this estimates g RMS, NOT a PSD and not velocity.
    """
    if not isinstance(samples, (list, tuple)):
        raise ValueError("samples must be a list or tuple")
    n = len(samples)
    if n < 8 or n > MAX_FFT_SAMPLES or n & (n - 1):
        raise ValueError("sample count must be power-of-two in [8, 8192]")
    if any(type(v) not in (int, float) or not isfinite(v) for v in samples):
        raise ValueError("all samples must be finite real numbers")
    if type(sample_rate_hz) is not int or sample_rate_hz <= 2 * BAND_HIGH_HZ:
        raise ValueError("sample_rate_hz must exceed 800 Hz to cover band")
    if type(rpm) not in (float, int) or not isfinite(rpm) or rpm <= 0:
        raise ValueError("rpm must be finite and positive")
    shaft = rpm / 60.0
    nyquist = sample_rate_hz / 2.0
    if shaft * 2 >= nyquist:
        raise ValueError("2x shaft frequency must be below Nyquist")

    mean = sum(samples) / n
    window = [0.5 - 0.5 * cos(2 * pi * i / n) for i in range(n)]
    fft = _fft_radix2([complex((v - mean) * window[i]) for i, v in enumerate(samples)])
    df = sample_rate_hz / n
    weight_sum = sum(window)
    squared_weight_sum = sum(w * w for w in window)

    def amplitude(target_hz: float) -> float:
        mid = target_hz / df
        lo = max(1, int(mid) - 1)
        hi = min(n // 2 - 1, int(mid) + 2)
        return 2 * max((abs(fft[k]) for k in range(lo, hi + 1)), default=0.0) / weight_sum

    power = []
    for k in range(n // 2 + 1):
        factor = 1 if k in (0, n // 2) else 2
        power.append(factor * abs(fft[k]) ** 2 / (n * squared_weight_sum))
    dominant_bin = max(range(1, n // 2 + 1), key=lambda k: power[k])
    band_energy = sum(p for k, p in enumerate(power) if BAND_LOW_HZ <= k * df <= BAND_HIGH_HZ)
    return {
        "spectral_window": "hann",
        "spectral_bin_hz": round(df, 5),
        "dominant_frequency_hz": round(dominant_bin * df, 4) if power[dominant_bin] > 1e-24 else 0.0,
        "shaft_1x_amplitude_g": round(amplitude(shaft), 4),
        "shaft_2x_amplitude_g": round(amplitude(2 * shaft), 4),
        "band_80_400_rms_g": round(sqrt(band_energy), 4),
    }
