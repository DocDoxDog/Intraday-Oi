"""Typed, evidence-first contracts for Market Analyst V3.

The LLM may interpret these objects, but deterministic upstream data remains authoritative.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

Regime = Literal["TREND_UP","TREND_DOWN","RANGE","COMPRESSION","EXPANSION","REVERSAL","EVENT_DRIVEN","LIQUIDITY_VACUUM","MIXED","UNKNOWN"]
Bias = Literal["BULLISH","BEARISH","NEUTRAL"]
Severity = Literal["LOW","MEDIUM","HIGH"]

@dataclass(frozen=True)
class Fact:
    id: str
    domain: str
    statement: str
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 1.0

@dataclass(frozen=True)
class Interpretation:
    id: str
    statement: str
    supports: tuple[str, ...] = ()
    confidence: float = 0.0
    epistemic_status: Literal["INTERPRETATION","HYPOTHESIS"] = "INTERPRETATION"

@dataclass(frozen=True)
class Conflict:
    id: str
    domains: tuple[str, ...]
    severity: Severity
    description: str
    resolution: str

@dataclass(frozen=True)
class RegimeAssessment:
    state: Regime
    confidence: float
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

@dataclass(frozen=True)
class Scenario:
    id: str
    bias: Bias
    priority: Literal["BASE","ALTERNATIVE","INVALIDATION"]
    conditions: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0

@dataclass(frozen=True)
class TradePlan:
    state: Literal["WAIT","CONDITIONAL","READY"] = "WAIT"
    long: dict[str, Any] = field(default_factory=dict)
    short: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class AnalystV3:
    analysis_id: str
    as_of: str
    product: str
    regime: RegimeAssessment
    facts: tuple[Fact, ...] = ()
    interpretations: tuple[Interpretation, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    scenarios: tuple[Scenario, ...] = ()
    trade_plan: TradePlan = field(default_factory=TradePlan)
    why_not_long: tuple[str, ...] = ()
    why_not_short: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    narrative: dict[str, str] = field(default_factory=dict)

def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
