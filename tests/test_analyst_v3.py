from intelligence.analysis.reasoning import build_analysis
from intelligence.analysis.regime import assess_regime

def test_unknown_regime_is_fail_closed():
    r=assess_regime({})
    assert r.state=="UNKNOWN"
    assert r.confidence==0.0

def test_conflicting_structure_and_options_is_explicit():
    state={"technical":{"timeframes":{"h1":{"trend":"bullish"},"m15":{"trend":"bullish"},"m5":{"trend":"bullish"}}}}
    evidence={
      "E1":{"domain":"TECHNICAL","statement":"Bullish BOS on M15"},
      "E2":{"domain":"OPTIONS","statement":"Negative gamma is bearish / pressuring"}
    }
    out=build_analysis(product="GC",as_of="2026-10-06T10:00:00Z",market_state=state,evidence=evidence)
    assert out["regime"]["state"]=="TREND_UP"
    assert out["conflicts"][0]["severity"]=="HIGH"
    assert out["trade_plan"]["state"]=="WAIT"

def test_evidence_is_preserved_as_source_refs():
    out=build_analysis(product="GC",as_of="x",market_state={},evidence={"E1":{"domain":"PRICE","statement":"Price observed"}})
    assert out["facts"][0]["evidence_refs"]==["E1"]
