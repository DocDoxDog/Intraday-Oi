from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScenarioPlan:
    scenario_id: str
    market: str
    directional_bias: str
    trigger: tuple[str, ...]
    confirmation: tuple[str, ...]
    invalidation: tuple[str, ...]
    key_levels: tuple[float, ...]
    risk_factors: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    confidence: float
    valid_until: datetime
    version: str
    status: str = "ACTIVE"
