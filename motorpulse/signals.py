"""Synthetic acceleration signals with a documented shaft-speed frequency model.

All returned sample values are acceleration in units of standard gravity (g).
This is a deterministic educational fixture, NOT a physical machinery model.
"""

from __future__ import annotations

from math import cos, exp, isfinite, pi, sin
from random import Random

BEARING_IMPACT_ORDER = 4.8  # invented illustrative ratio; not a bearing-geometry BPFO
NOISE_STD_G = 0.014
# 1x and 2x shaft harmonics, in peak acceleration g.
HARMONIC_AMPLITUDES_G = {
    "healthy": (0.12, 0.015),
    "imbalance": (0.62, 0.020),
    "bearing_wear": (0.22, 0.025),
    "misalignment": (0.14, 0.28),
    "overload": (0.20, 0.025),
}


def generate_vibration(
    rpm: float,
    scenario: str,
    rng: Random,
    *,
    sample_rate_hz: int = 1024,
    sample_count: int = 1024,
    severity: float = 1.0,
) -> list[float]:
    """Produce equally spaced samples at times i / sample_rate_hz.

    Shaft 1x frequency is rpm/60 Hz, 2x is its second harmonic.
    'imbalance' emphasizes 1x; 'misalignment' emphasizes 2x.
    'bearing_wear' adds smooth, phase-repeating illustrative impacts at 4.8x.
    No geometry or field measurements justify that assumed impact order.
    All modeled cyclic frequencies must remain strictly below Nyquist;
    no artificial anti-alias filter or sensor bandwidth model is provided.
    """
    if type(rpm) not in (float, int) or not isfinite(rpm) or rpm <= 0:
        raise ValueError("rpm must be a finite positive number")
    if type(severity) not in (int, float) or not isfinite(severity) or not 0 <= severity <= 1:
        raise ValueError("severity must be between 0 and 1")
    if scenario not in HARMONIC_AMPLITUDES_G:
        raise ValueError("unknown waveform scenario")
    if not isinstance(rng, Random):
        raise TypeError("rng must be random.Random")
    if type(sample_rate_hz) is not int or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be a positive integer")
    if type(sample_count) is not int or sample_count < 2:
        raise ValueError("sample_count must be an integer >= 2")
    shaft_hz = rpm / 60.0
    max_frequency_hz = shaft_hz * (BEARING_IMPACT_ORDER if scenario == "bearing_wear" else 2)
    if max_frequency_hz >= sample_rate_hz / 2:
        raise ValueError("modeled frequency must be below Nyquist; increase sample_rate_hz")

    normal_1x, normal_2x = HARMONIC_AMPLITUDES_G["healthy"]
    target_1x, target_2x = HARMONIC_AMPLITUDES_G[scenario]
    amp_1x = normal_1x + severity * (target_1x - normal_1x)
    amp_2x = normal_2x + severity * (target_2x - normal_2x)
    samples = []
    for index in range(sample_count):
        t = index / sample_rate_hz
        angle = 2 * pi * shaft_hz * t
        value = amp_1x * sin(angle) + amp_2x * sin(2 * angle + 0.35)
        if scenario == "bearing_wear":
            # Broad periodic Gaussian-shaped pulses rather than single-sample spikes.
            # This shape still contains higher-frequency components: no claim of
            # anti-alias filtering or physical impact-response fidelity.
            phase = (BEARING_IMPACT_ORDER * shaft_hz * t) % 1.0
            phase_distance = min(phase, 1.0 - phase)
            value += severity * exp(-0.5 * (phase_distance / 0.085) ** 2)
        value += rng.gauss(0, NOISE_STD_G)
        samples.append(value)
    return samples


def harmonic_amplitude_g(samples: list[float], frequency_hz: float, sample_rate_hz: int) -> float:
    """Single-frequency projection for diagnostics (exact for bin-centered tones).

    This is not an FFT library: for non-bin-centered frequencies and noisy
    finite windows, spectral leakage affects interpretation.
    """
    if not samples or type(frequency_hz) not in (int, float) or not isfinite(frequency_hz):
        raise ValueError("samples must be nonempty and frequency finite")
    if type(sample_rate_hz) is not int or sample_rate_hz <= 0 or not 0 < frequency_hz < sample_rate_hz / 2:
        raise ValueError("projection frequency must lie inside (0, Nyquist)")
    n = len(samples)
    re = sum(v * cos(2 * pi * frequency_hz * i / sample_rate_hz) for i, v in enumerate(samples))
    im = sum(v * sin(2 * pi * frequency_hz * i / sample_rate_hz) for i, v in enumerate(samples))
    return 2 * (re * re + im * im) ** 0.5 / n
