"""Deterministic synthetic signals and transparent (non-ML) anomaly rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt
from random import Random

from .schema import SAMPLE_COUNT, SAMPLE_RATE_HZ, SCHEMA_VERSION, SENSOR_UNITS
from .signals import generate_vibration

DEFAULT_START_TIME_UTC = datetime(2026, 1, 1, tzinfo=timezone.utc)


def parse_start_time_utc(value: str) -> datetime:
    """Parse a timezone-aware ISO 8601 instant with an explicit UTC offset."""
    if not isinstance(value, str):
        raise ValueError("start_time_utc must be an ISO 8601 UTC string")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("start_time_utc must be ISO 8601") from exc
    if moment.utcoffset() != timedelta(0):
        raise ValueError("start_time_utc must be explicitly UTC (+00:00 or Z)")
    return moment.astimezone(timezone.utc)


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
    start_time_utc: datetime = DEFAULT_START_TIME_UTC
    step_seconds: float = 1.5
    _step_microseconds: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if type(self.tick) is not int or self.tick < 0:
            raise ValueError("tick must be a nonnegative integer")
        if not isinstance(self.start_time_utc, datetime) or self.start_time_utc.utcoffset() != timedelta(0):
            raise ValueError("start_time_utc must be a timezone-aware UTC datetime")
        self.start_time_utc = self.start_time_utc.astimezone(timezone.utc)
        if (type(self.step_seconds) not in (int, float) or not isfinite(self.step_seconds)
                or not 0 < self.step_seconds <= 86400):
            raise ValueError("step_seconds must be finite and in (0, 86400]")
        raw_microseconds = self.step_seconds * 1_000_000
        microseconds = round(raw_microseconds)
        if microseconds < 1 or abs(raw_microseconds - microseconds) > 1e-7:
            raise ValueError("step_seconds must resolve to whole microseconds")
        self._step_microseconds = microseconds
        self.step_seconds = microseconds / 1_000_000

    def timestamp_for_tick(self, tick: int) -> str:
        """Tick 1 is at the configured start; later ticks use virtual time."""
        if type(tick) is not int or tick < 1:
            raise ValueError("tick must be a positive integer")
        try:
            time = self.start_time_utc + timedelta(microseconds=(tick - 1) * self._step_microseconds)
        except OverflowError as exc:
            raise ValueError("virtual simulation clock overflow") from exc
        return time.isoformat()

    def sample_asset(self, asset_id: str, name: str, scenario: str,
                     *, timestamp_utc: str | None = None) -> dict:
        # Re-seeding by tick+asset ensures repeatable outputs across processes.
        rng = Random(f"{self.seed}:{self.tick}:{asset_id}")
        base_rpm = 1480 + rng.uniform(-24, 24)
        temp = 47 + rng.uniform(-3, 3)
        if scenario == "imbalance":
            temp += 13
        elif scenario == "bearing_wear":
            temp += 35
        samples = generate_vibration(base_rpm, scenario, rng,
                                     sample_rate_hz=SAMPLE_RATE_HZ,
                                     sample_count=SAMPLE_COUNT)
        sensor = features(samples)
        health, reasons = classify(sensor["rms_g"], temp, sensor["crest_factor"])
        if timestamp_utc is None:
            timestamp_utc = self.timestamp_for_tick(max(1, self.tick))
        return {
            "event_id": f"sim:{self.seed}:{asset_id}:{self.tick}",
            "asset_id": asset_id,
            "name": name,
            "scenario": scenario,
            "source": "synthetic",
            "timestamp_utc": timestamp_utc,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "sample_count": SAMPLE_COUNT,
            "window_duration_s": SAMPLE_COUNT / SAMPLE_RATE_HZ,
            "shaft_frequency_hz": round(base_rpm / 60, 4),
            "units": SENSOR_UNITS.copy(),
            "rpm": round(base_rpm, 1),
            "temperature_c": round(temp, 1),
            **sensor,
            "health": health,
            "reasons": reasons,
        }

    def step(self) -> dict:
        self.tick += 1
        recorded_at_utc = self.timestamp_for_tick(self.tick)
        assets = [self.sample_asset(*asset, timestamp_utc=recorded_at_utc)
                  for asset in ASSETS]
        return {
            "schema_version": SCHEMA_VERSION,
            "source": "synthetic",
            "tick": self.tick,
            "recorded_at_utc": recorded_at_utc,
            "assets": assets,
        }
