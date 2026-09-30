from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketAnalysis:
    market_context: str
    what_changed: str
    why_it_matters: str
    key_levels: tuple[float, ...]
    risk_factors: tuple[str, ...]
    uncertainties: tuple[str, ...]
    evidence: tuple[str, ...]
    confidence: float
    generated_at: str
    model_version: str
    dataset_version: str
    calculation_version: str
