from src.reasoning_engine import build_reasoning_pack

def test_reasoning_pack_is_conditional_and_traceable():
    state = {
        "future_price": 4000.0, "cfd_price": 3998.0,
        "technical_context": {"confirmation": {"bias": "BULLISH", "htf_aligned": True}},
        "raw_series": {
            "totals": {"open_interest_view_call": 1200, "open_interest_view_put": 900},
            "gex": {"net_gex": -1000, "gamma_flip": 3980, "call_wall": 4020, "put_wall": 3960},
            "market_state": {"decision_framework": {"structural_bias": "BULLISH"},
                             "levels": {"resistance_current": 4020, "support_current": 3960}},
        },
    }
    pack = build_reasoning_pack(state, {"today": {"count": 3}, "hour_ago": {}, "yesterday": {}})
    assert pack["version"].startswith("reasoning-v5")
    assert pack["status"] == "WAIT_FOR_CONFIRMATION"
    assert pack["directional_context"] == "BULLISH"
    assert pack["conflicts"][0]["id"] == "negative-gamma"
    assert pack["scenarios"][0]["trigger"] == 4020
    assert pack["scenarios"][1]["invalidation"] == 4020
    assert all("evidence_refs" in item for item in pack["evidence"])

def test_missing_price_never_gets_fake_trigger():
    pack = build_reasoning_pack({"raw_series": {}}, None)
    assert pack["status"] == "DATA_INSUFFICIENT"
    assert pack["scenarios"][0]["trigger"] is None
    assert pack["scenarios"][1]["trigger"] is None
