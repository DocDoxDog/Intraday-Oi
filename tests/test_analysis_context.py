from datetime import datetime, timezone
from types import SimpleNamespace

from intelligence.analysis.context import build_analysis_context


def test_analysis_context_contains_only_structured_market_facts():
    state = SimpleNamespace(
        symbol="GC", price=3800.0, oi=1000.0, oi_change=10.0, gex=50.0, dex=25.0,
        iv=20.0, realized_vol=18.0, gamma_flip=3790.0, call_wall=3850.0,
        put_wall=3750.0, positioning_regime="UNKNOWN", volatility_regime="NORMAL",
        data_status="VALID", data_quality=1.0, data_age_seconds=3.0,
        as_of=datetime(2026, 10, 1, tzinfo=timezone.utc),
        dataset_version="d1", calculation_version="c1",
        sign_convention="DEALER_SHORT_PUBLIC", gamma_source="quikstrike",
        assumptions=("dealer_positioning_not_observed",), evidence=("GEX_STATUS:ok",),
    )
    context = build_analysis_context(
        market_state=state, news=[{"headline": "Fed statement", "url": "https://example.test/fed"}]
    )
    assert context["market_state"]["price"] == 3800.0
    assert context["market_state"]["call_wall"] == 3850.0
    assert "Every numeric level must originate in market_state." in context["constraints"]