from datetime import datetime, timezone, timedelta

from intelligence.scenario.models import ScenarioPlan
from intelligence.scenario.update import update_scenario_status


def scenario():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return ScenarioPlan(
        scenario_id="GC-A", market="GC", directional_bias="CONDITIONAL_UP",
        trigger=("price accepts above:100",), confirmation=("valid",),
        invalidation=("price rejects below:90",), key_levels=(90.0, 100.0),
        risk_factors=("conditional",), supporting_evidence=(),
        contradicting_evidence=(), confidence=0.0,
        valid_until=now + timedelta(hours=1), version="v1",
    )


def test_scenario_expires():
    s = scenario()
    out = update_scenario_status(s, current_price=100, material_change=True, now=s.valid_until + timedelta(minutes=1))
    assert out.status == "EXPIRED"


def test_scenario_invalidation_is_explicit():
    s = scenario()
    out = update_scenario_status(s, current_price=85, material_change=True, now=datetime(2026, 10, 1, 0, 10, tzinfo=timezone.utc))
    assert out.status == "INVALIDATED"