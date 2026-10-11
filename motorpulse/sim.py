"""Deterministic synthetic signals and transparent (non-ML) anomaly rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite, pi, sin, sqrt
from random import Random

from .schema import SAMPLE_COUNT, SAMPLE_RATE_HZ, SCHEMA_VERSION, SENSOR_UNITS
from .signals import generate_vibration
from .spectral import ROLLING_WINDOW_TICKS, spectral_features
from .scenarios import AssetScenario, DEFAULT_ASSETS

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


ASSETS = tuple((a.asset_id, a.name, a.scenario) for a in DEFAULT_ASSETS)


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
    assets: tuple[AssetScenario, ...] = DEFAULT_ASSETS
    _step_microseconds: int = field(init=False, repr=False)
    _rolling_history: dict[str, list[tuple[float, float]]] = field(default_factory=dict, init=False, repr=False)

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
        if (not isinstance(self.assets, tuple) or not 1 <= len(self.assets) <= 12
                or any(not isinstance(a, AssetScenario) for a in self.assets)
                or len({a.asset_id for a in self.assets}) != len(self.assets)):
            raise ValueError("assets must contain 1 to 12 uniquely identified AssetScenario objects")
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
                     *, timestamp_utc: str | None = None, severity: float = 1.0,
                     operating_config: AssetScenario | None = None) -> dict:
        # Re-seeding by tick+asset ensures repeatable outputs across processes.
        rng = Random(f"{self.seed}:{self.tick}:{asset_id}")
        base_rpm = 1480 + rng.uniform(-24, 24)
        temp = 47 + rng.uniform(-3, 3)
        # These sinusoidal profiles are deterministic test conditions, not
        # physical motor load dynamics; defaults preserve historical behavior.
        cfg = operating_config
        phase = self.tick - 1
        speed_factor = 1 + (cfg.speed_variation_pct if cfg else 0) * sin(2 * pi * phase / 24)
        load_factor = 1 + (cfg.load_variation_pct if cfg else 0) * sin(2 * pi * phase / 32 + 1)
        base_rpm *= speed_factor
        temp += (load_factor - 1) * 12
        if scenario == "imbalance":
            temp += 13 * severity
        elif scenario == "bearing_wear":
            temp += 35 * severity
        elif scenario == "misalignment":
            temp += 9 * severity
        elif scenario == "overload":
            temp += 50 * severity
        samples = generate_vibration(base_rpm, scenario, rng,
                                     sample_rate_hz=SAMPLE_RATE_HZ,
                                     sample_count=SAMPLE_COUNT, severity=severity,
                                     noise_std_g=cfg.sensor_noise_g if cfg else 0.014)
        # Loaded torque affects the mock vibration magnitude, separately from
        # the machine-fault 'severity' label. No calibrated transfer function.
        if cfg and cfg.load_variation_pct:
            samples = [sample * (1 + 0.6 * (load_factor - 1)) for sample in samples]
        drift_g = max(-0.5, min(0.5, (cfg.sensor_drift_g_per_tick if cfg else 0) * phase))
        if drift_g:
            samples = [sample + drift_g for sample in samples]
        missing = bool(cfg and cfg.sensor_event_active("missing", self.tick))
        outlier = bool(cfg and cfg.sensor_event_active("outlier", self.tick))
        if outlier and not missing:
            samples[SAMPLE_COUNT // 3] += cfg.sensor_outlier_g
        if missing:
            sensor = {key: None for key in (
                "rms_g", "peak_to_peak_g", "crest_factor", "spectral_bin_hz",
                "dominant_frequency_hz", "shaft_1x_amplitude_g",
                "shaft_2x_amplitude_g", "band_80_400_rms_g")}
            sensor["spectral_window"] = "hann"
            health, reasons = "unavailable", ["vibration sensor reading missing; machine assessment suppressed"]
            quality, quality_reasons = "missing", ["simulated vibration sensor dropout"]
        else:
            sensor = features(samples)
            sensor.update(spectral_features(samples, base_rpm, sample_rate_hz=SAMPLE_RATE_HZ))
            if outlier:
                health, reasons = "suspect", ["vibration sensor outlier; machine assessment suppressed"]
                quality, quality_reasons = "outlier", ["simulated vibration sensor impulse"]
            else:
                health, reasons = classify(sensor["rms_g"], temp, sensor["crest_factor"])
                quality, quality_reasons = "good", []
        if missing and outlier:
            quality_reasons.append("outlier scheduled but masked by missing reading")
        if timestamp_utc is None:
            timestamp_utc = self.timestamp_for_tick(max(1, self.tick))
        return {
            "event_id": f"sim:{self.seed}:{asset_id}:{self.tick}",
            "asset_id": asset_id,
            "name": name,
            "scenario": scenario,
            "severity": severity,
            "source": "synthetic",
            "timestamp_utc": timestamp_utc,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "sample_count": SAMPLE_COUNT,
            "window_duration_s": SAMPLE_COUNT / SAMPLE_RATE_HZ,
            "shaft_frequency_hz": round(base_rpm / 60, 4),
            "units": SENSOR_UNITS.copy(),
            "rpm": round(base_rpm, 1),
            "temperature_c": round(temp, 1),
            "load_factor": round(load_factor, 5),
            "sensor_quality": quality,
            "sensor_quality_reasons": quality_reasons,
            "sensor_drift_g": round(drift_g, 6),
            **sensor,
            "health": health,
            "reasons": reasons,
        }

    def step(self) -> dict:
        self.tick += 1
        recorded_at_utc = self.timestamp_for_tick(self.tick)
        assets = []
        for config in self.assets:
            active_scenario, active_severity = config.effective(self.tick)
            row = self.sample_asset(config.asset_id, config.name, active_scenario,
                                    timestamp_utc=recorded_at_utc,
                                    severity=active_severity,
                                    operating_config=config)
            history = self._rolling_history.setdefault(config.asset_id, [])
            history.append((row["rms_g"], row["temperature_c"]))
            if len(history) > ROLLING_WINDOW_TICKS:
                del history[:-ROLLING_WINDOW_TICKS]
            valid_rms = [value[0] for value in history if value[0] is not None]
            row.update({
                "rolling_window_ticks": ROLLING_WINDOW_TICKS,
                "rolling_observations": len(history),
                "rolling_valid_observations": len(valid_rms),
                "rolling_rms_mean_g": (
                    round(sum(valid_rms) / len(valid_rms), 4)
                    if valid_rms and row["rms_g"] is not None else None
                ),
                "rolling_temperature_mean_c": round(sum(value[1] for value in history) / len(history), 4),
                "configured_scenario": config.scenario,
                "configured_severity": float(config.severity),
                "onset_tick": config.onset_tick,
                "duration_ticks": config.duration_ticks,
                "progression": config.progression,
                "start_severity": float(config.start_severity),
                "ramp_ticks": config.ramp_ticks,
                "ramp_fraction": config.ramp_fraction(self.tick),
                "fault_phase": config.phase(self.tick),
                "operating_config": {
                    "speed_variation_pct": float(config.speed_variation_pct),
                    "load_variation_pct": float(config.load_variation_pct),
                    "sensor_noise_g": float(config.sensor_noise_g),
                    "sensor_drift_g_per_tick": float(config.sensor_drift_g_per_tick),
                },
            })
            assets.append(row)
        return {
            "schema_version": SCHEMA_VERSION,
            "source": "synthetic",
            "tick": self.tick,
            "recorded_at_utc": recorded_at_utc,
            "assets": assets,
        }
