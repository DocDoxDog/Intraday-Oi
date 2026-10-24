from src.regime_fingerprint import build_regime_fingerprint
from src.episodic_memory import retrieve_episodes
from src.research_gate import purged_split, cost_gate, promotion_decision
from src.v6_intelligence import build_v6_intelligence

def state():
    return {"observed_at":"2026-10-21T10:00:00+00:00","raw_series":{"market_state":{
        "technical":{"h4":{"trend":"bullish"},"h1":{"trend":"bullish"}},
        "volatility":{"iv":22.0},"gamma":{"net_gex":-10.0},
        "auction":{"location":"ABOVE_VALUE","state":"ACCEPTANCE_ABOVE"},
        "order_flow":{"aggression":{"delta":5.0}},
        "news":[]
    }}}

def test_regime_fingerprint_is_deterministic():
    a = build_regime_fingerprint(state())
    b = build_regime_fingerprint(state())
    assert isinstance(a, dict)
    assert isinstance(b, dict)
    assert a.get("fingerprint_id") == b.get("fingerprint_id")
    assert a.get("trend") == "BULLISH"
    assert a.get("gamma") == "NEGATIVE_GAMMA"

def test_future_episode_is_rejected():
    current={"asof":"2026-10-21T10:00:00+00:00","fingerprint":{"trend":"BULLISH"}}
    episodes=[{"episode_id":"future","information_time":"2026-10-21T10:01:00+00:00","fingerprint":{"trend":"BULLISH"}}]
    assert retrieve_episodes(current,episodes)==[]

def test_past_episode_hides_outcome():
    current={"asof":"2026-10-21T10:00:00+00:00","fingerprint":{"trend":"BULLISH"}}
    episodes=[{"episode_id":"past","information_time":"2026-10-21T09:00:00+00:00","fingerprint":{"trend":"BULLISH"},"outcome":{"forward_return":99}}]
    got=retrieve_episodes(current,episodes)
    assert got[0]["episode_id"]=="past" and "outcome" not in got[0]

def test_purged_embargoed_split():
    rows=[{"information_time":f"2026-10-21T{h:02d}:00:00+00:00"} for h in range(8,14)]
    got=purged_split(rows,"2026-10-21T10:00:00+00:00","2026-10-21T11:00:00+00:00",60)
    assert len(got["train"])==2 and len(got["test"])==2

def test_cost_gate():
    assert cost_gate(0.5,0.7)["status"]=="FAIL"
    assert cost_gate(1.0,0.7)["status"]=="PASS"

def test_promotion_never_authorizes_production():
    out=promotion_decision(measurement_pass=True,association_pass=True,oos_pass=True,cost_pass=True,calibration_pass=True)
    assert out["status"]=="PROMOTE" and out["production_change_allowed"] is False

def test_v6_bundle_contains_governance():
    out=build_v6_intelligence(state())
    assert out["version"]=="market-intelligence-v6.0"
    assert out["research_policy"]["oos_required"] is True
    assert out["execution_authority"]=="NONE"
