"""Validated immutable synthetic motor scenarios (MP-007).

These are demo fault amplitudes, not physical severity calibration. Progressive
fault growth is reserved for MP-020; severity here is a constant during a fault.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import Any

SCENARIOS = ("healthy", "imbalance", "bearing_wear", "misalignment", "overload")
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

    def effective(self, tick: int) -> tuple[str, float]:
        """Outside a fault's active interval, the asset behaves as healthy."""
        if (self.scenario == "healthy" or self.severity == 0
                or tick < self.onset_tick
                or (self.duration_ticks is not None and tick >= self.onset_tick + self.duration_ticks)):
            return "healthy", 0.0
        return self.scenario, float(self.severity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "scenario": self.scenario,
            "severity": float(self.severity),
            "onset_tick": self.onset_tick,
            "duration_ticks": self.duration_ticks,
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
