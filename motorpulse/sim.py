"""Deterministic synthetic signals and transparent (non-ML) anomaly rules."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import pi, sin, sqrt
from random import Random

from .schema import SAMPLE_COUNT, SAMPLE_RATE_HZ, SCHEMA_VERSION, SENSOR_UNITS

ASSETS = (
    ("MTR-01", "Conveyor motor", "healthy"),
    ("MTR-02", "Pump motor", "imbalance"),
    ("MTR-03", "Fan motor", "bearing_wear"),
)


def features(samples: list[float]) -> dict[str, float]:
    if not samples:
        raise ValueError("samples must not be empty")
    rms = sqrt(sum(x * x for x in samples) / len(samples))
    peak = max(abs(x) for x in samples)
    return {
        "rms_g": round(rms, 4),
        "peak_to_peak_g": round(max(samples) - min(samples), 4),
        "crest_factor": round(peak / rms, 4) if rms else 0.0,
    }


def classify(rms_g: float, temperature_c: float, crest_factor: float) -> tuple[str, list[str]]:
    """Demo thresholds only: not calibrated to industrial assets."""
    reasons: list[str] = []
    if rms_g >= 0.36:
        reasons.append("elevated vibration RMS")
    if temperature_c >= 82.0:
        reasons.append("high temperature")
    if crest_factor >= 2.7 and rms_g >= 0.20:
        reasons.append("impulsive vibration waveform")
    if not reasons:
        return "normal", []
    if rms_g >= 0.55 or temperature_c >= 92.0:
        return "critical", reasons
    return "warning", reasons


@dataclass
class MotorSimulator:
    seed: int = 42
    tick: int = 0

    def sample_asset(self, asset_id: str, name: str, scenario: str,
                     *, timestamp_utc: str | None = None) -> dict:
        # Re-seeding by tick+asset ensures repeatable outputs across processes.
        rng = Random(f"{self.seed}:{self.tick}:{asset_id}")
        base_rpm = 1480 + rng.uniform(-24, 24)
        temp = 47 + rng.uniform(-3, 3)
        amplitude = 0.12
        impulsive = False
        if scenario == "imbalance":
            amplitude = 0.62
            temp += 13
        elif scenario == "bearing_wear":
            amplitude = 0.43
            temp += 35
            impulsive = True
        samples = []
        for i in range(SAMPLE_COUNT):
            waveform = amplitude * sin(2 * pi * i / 16) + rng.gauss(0, 0.014)
            if impulsive and i % 31 == 0:
                waveform += 1.0
            samples.append(waveform)
        sensor = features(samples)
        health, reasons = classify(sensor["rms_g"], temp, sensor["crest_factor"])
        if timestamp_utc is None:
            timestamp_utc = datetime.now(timezone.utc).isoformat()
        return {
            "event_id": f"sim:{self.seed}:{asset_id}:{self.tick}",
            "asset_id": asset_id,
            "name": name,
            "scenario": scenario,
            "source": "synthetic",
            "timestamp_utc": timestamp_utc,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "sample_count": SAMPLE_COUNT,
            "units": SENSOR_UNITS.copy(),
            "rpm": round(base_rpm, 1),
            "temperature_c": round(temp, 1),
            **sensor,
            "health": health,
            "reasons": reasons,
        }

    def step(self) -> dict:
        self.tick += 1
        recorded_at_utc = datetime.now(timezone.utc).isoformat()
        assets = [self.sample_asset(*asset, timestamp_utc=recorded_at_utc)
                  for asset in ASSETS]
        return {
            "schema_version": SCHEMA_VERSION,
            "source": "synthetic",
            "tick": self.tick,
            "recorded_at_utc": recorded_at_utc,
            "assets": assets,
        }
