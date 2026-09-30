from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from intelligence.scenario.models import ScenarioPlan


def build_scenarios(
    *,
    market: str,
    price: float | None,
    gamma_flip: float | None,
    call_wall: float | None,
    put_wall: float | None,
    evidence: tuple[str, ...],
    contradictions: tuple[str, ...],
    horizon_minutes: int = 60,
    version: str = "scenario-v1",
) -> tuple[ScenarioPlan, ...]:
    levels = tuple(x for x in (gamma_flip, call_wall, put_wall) if x is not None)
    if price is None or not levels:
        return ()

    valid_until = datetime.now(timezone.utc) + timedelta(minutes=horizon_minutes)
    return (
        ScenarioPlan(
            scenario_id=f"{market}-A",
            market=market,
            directional_bias="CONDITIONAL_UP",
            trigger=(f"price_accepts_above:{max(levels)}",),
            confirmation=("market_state_remains_valid",),
            invalidation=(f"price_rejects_below:{min(levels)}",),
            key_levels=levels,
            risk_factors=("scenario_is_conditional", "no_outcome_guarantee"),
            supporting_evidence=evidence,
            contradicting_evidence=contradictions,
            confidence=0.0,
            valid_until=valid_until,
            version=version,
        ),
        ScenarioPlan(
            scenario_id=f"{market}-B",
            market=market,
            directional_bias="CONDITIONAL_DOWN",
            trigger=(f"price_rejects_below:{min(levels)}",),
            confirmation=("market_state_remains_valid",),
            invalidation=(f"price_accepts_above:{max(levels)}",),
            key_levels=levels,
            risk_factors=("scenario_is_conditional", "no_outcome_guarantee"),
            supporting_evidence=evidence,
            contradicting_evidence=contradictions,
            confidence=0.0,
            valid_until=valid_until,
            version=version,
        ),
    )
