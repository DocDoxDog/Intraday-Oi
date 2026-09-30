from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from intelligence.scenario.models import ScenarioPlan


def update_scenario_status(
    scenario: ScenarioPlan,
    *,
    current_price: float | None,
    material_change: bool,
    now: datetime | None = None,
) -> ScenarioPlan:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")

    if current >= scenario.valid_until:
        return replace(scenario, status="EXPIRED")

    if not material_change:
        return scenario

    levels = sorted(scenario.key_levels)
    if current_price is not None and levels:
        if scenario.directional_bias == "CONDITIONAL_UP" and current_price < levels[0]:
            return replace(scenario, status="INVALIDATED")
        if scenario.directional_bias == "CONDITIONAL_DOWN" and current_price > levels[-1]:
            return replace(scenario, status="INVALIDATED")

    return replace(scenario, status="UPDATED")
