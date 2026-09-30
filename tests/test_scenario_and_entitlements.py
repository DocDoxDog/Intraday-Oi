from datetime import datetime, timezone, timedelta

from intelligence.customer.entitlements import Entitlement, check_entitlement
from intelligence.scenario.engine import build_scenarios


def test_scenario_engine_is_conditional():
    scenarios = build_scenarios(
        market="GC",
        price=3800,
        gamma_flip=3790,
        call_wall=3850,
        put_wall=3750,
        evidence=("GEX observed",),
        contradictions=("IV source incomplete",),
        horizon_minutes=30,
    )
    assert len(scenarios) == 2
    assert all(s.directional_bias.startswith("CONDITIONAL_") for s in scenarios)
    assert all("no_outcome_guarantee" in s.risk_factors for s in scenarios)


def test_entitlement_is_server_side_decision():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    entitlement = Entitlement("org-1", "gex_realtime", True, now - timedelta(hours=1))
    assert check_entitlement((entitlement,), organization_id="org-1", feature="gex_realtime", now=now).allowed
    assert not check_entitlement((entitlement,), organization_id="org-2", feature="gex_realtime", now=now).allowed
