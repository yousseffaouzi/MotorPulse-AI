"""Validated synthetic motor scenarios and timelines (MP-007 / MP-020).

These are demo fault amplitudes, not physical severity calibration. Progression profiles are teaching curves, not actual bearing wear models.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import expm1, isfinite
import re
from typing import Any

SCENARIOS = ("healthy", "imbalance", "bearing_wear", "misalignment", "overload")
PROGRESSION_PROFILES = ("constant", "linear", "exponential")
EXPONENTIAL_STEEPNESS = 4.0  # educational curve shape, not empirical wear
MAX_ASSETS = 12
ASSET_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{1,23}$")


@dataclass(frozen=True)
class AssetScenario:
    asset_id: str
    name: str
    scenario: str = "healthy"
    severity: float = 0.0
    onset_tick: int = 1
    duration_ticks: int | None = None
    progression: str = "constant"
    start_severity: float = 0.0
    ramp_ticks: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not ASSET_ID_PATTERN.fullmatch(self.asset_id):
            raise ValueError("asset_id must match [A-Z][A-Z0-9_-]{1,23}")
        if not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 80:
            raise ValueError("name must contain 1 to 80 characters")
        if not isinstance(self.scenario, str) or self.scenario not in SCENARIOS:
            raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
        if type(self.severity) not in (int, float) or not isfinite(self.severity) or not 0 <= self.severity <= 1:
            raise ValueError("severity must be a finite number between 0 and 1")
        if self.scenario == "healthy" and self.severity != 0:
            raise ValueError("healthy scenario must have severity 0")
        if type(self.onset_tick) is not int or not 1 <= self.onset_tick <= 100000:
            raise ValueError("onset_tick must be an integer between 1 and 100000")
        if self.duration_ticks is not None and (
            type(self.duration_ticks) is not int or not 1 <= self.duration_ticks <= 100000
        ):
            raise ValueError("duration_ticks must be null or an integer between 1 and 100000")
        if not isinstance(self.progression, str) or self.progression not in PROGRESSION_PROFILES:
            raise ValueError("progression must be constant, linear or exponential")
        if type(self.start_severity) not in (int, float) or not isfinite(self.start_severity) or not 0 <= self.start_severity <= 1:
            raise ValueError("start_severity must be finite and in [0, 1]")
        if self.progression == "constant":
            if self.ramp_ticks is not None or self.start_severity != 0:
                raise ValueError("constant progression requires ramp_ticks=null and start_severity=0")
        else:
            if self.scenario == "healthy" or self.severity <= 0:
                raise ValueError("progressive faults must have a non-healthy scenario and positive target severity")
            if self.start_severity >= self.severity:
                raise ValueError("start_severity must be less than target severity")
            if type(self.ramp_ticks) is not int or not 2 <= self.ramp_ticks <= 100000:
                raise ValueError("ramp_ticks must be an integer between 2 and 100000")
            if self.duration_ticks is not None and self.duration_ticks < self.ramp_ticks:
                raise ValueError("duration_ticks must be >= ramp_ticks for a progressive fault")

    def phase(self, tick: int) -> str:
        """State of the synthetic scenario at one integer tick."""
        if type(tick) is not int or tick < 1:
            raise ValueError("tick must be a positive integer")
        if self.scenario == "healthy" or self.severity == 0:
            return "healthy"
        if tick < self.onset_tick:
            return "scheduled"
        if self.duration_ticks is not None and tick >= self.onset_tick + self.duration_ticks:
            return "ended"
        if self.progression != "constant" and tick < self.onset_tick + self.ramp_ticks - 1:
            return "ramping"
        return "steady"

    def ramp_fraction(self, tick: int) -> float:
        """Completion fraction while active; zero when outside."""
        phase = self.phase(tick)
        if phase not in ("ramping", "steady"):
            return 0.0
        if self.progression == "constant":
            return 1.0
        return min(1.0, (tick - self.onset_tick) / (self.ramp_ticks - 1))

    def effective(self, tick: int) -> tuple[str, float]:
        """Deterministic fault label and severity at this tick."""
        phase = self.phase(tick)
        if phase in ("healthy", "scheduled", "ended"):
            return "healthy", 0.0
        if self.progression == "constant":
            strength = float(self.severity)
        else:
            frac = self.ramp_fraction(tick)
            growth = frac if self.progression == "linear" else expm1(EXPONENTIAL_STEEPNESS * frac) / expm1(EXPONENTIAL_STEEPNESS)
            strength = self.start_severity + (self.severity - self.start_severity) * growth
        if strength <= 0:
            return "healthy", 0.0
        return self.scenario, float(min(self.severity, strength))

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "scenario": self.scenario,
            "severity": float(self.severity),
            "onset_tick": self.onset_tick,
            "duration_ticks": self.duration_ticks,
            "progression": self.progression,
            "start_severity": float(self.start_severity),
            "ramp_ticks": self.ramp_ticks,
        }


DEFAULT_ASSETS = (
    AssetScenario("MTR-01", "Conveyor motor"),
    AssetScenario("MTR-02", "Pump motor", "imbalance", 1.0),
    AssetScenario("MTR-03", "Fan motor", "bearing_wear", 1.0),
)


def parse_configuration(payload: object) -> tuple[AssetScenario, ...]:
    """Accept a complete, validated replacement configuration, not a partial patch."""
    if not isinstance(payload, dict) or set(payload) != {"assets"}:
        raise ValueError("configuration must be an object containing only 'assets'")
    rows = payload["assets"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ASSETS:
        raise ValueError(f"assets must be a list of 1 to {MAX_ASSETS} motors")
    accepted = set(AssetScenario.__dataclass_fields__)
    required = {"asset_id", "name", "scenario"}
    assets = []
    ids = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not required.issubset(row) or set(row) - accepted:
            raise ValueError(f"assets[{index}] must specify asset_id, name, scenario and valid optional fields")
        asset = AssetScenario(**row)
        if asset.asset_id in ids:
            raise ValueError(f"duplicate asset_id: {asset.asset_id}")
        ids.add(asset.asset_id)
        assets.append(asset)
    return tuple(assets)


def configuration_dict(assets: tuple[AssetScenario, ...]) -> dict[str, list[dict[str, Any]]]:
    return {"assets": [asset.to_dict() for asset in assets]}
