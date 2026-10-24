from src.evidence_fusion import build_evidence_fusion


def base_state():
    return {
        "raw_series": {
            "market_state": {
                "price": {"futures": 2300.0, "cfd": 2299.5},
                "levels": {"support_current": 2280.0, "resistance_current": 2315.0},
                "decision_framework": {"structural_bias": "BULLISH"},
                "technical": {"h4": {"trend": "bullish"}, "h1": {"trend": "bullish"}},
                "auction": {"poc": 2300.0, "vah": 2308.0, "val": 2288.0, "mode": "BAR_PROXY"},
                "gamma": {"net_gex": -100.0, "gamma_flip": 2305.0, "call_wall": 2320.0, "put_wall": 2275.0},
                "flow": {"oi_put": 1000.0, "oi_call": 1300.0, "oi_change_put": 100.0, "oi_change_call": 200.0},
                "volatility": {
                    "iv": 18.0,
                    "skew": 1.4,
                    "iv_term_structure": [{"dte": 2, "iv": 22.0}, {"dte": 10, "iv": 18.0}],
                    "smile": {"25d_put": 22.0, "atm": 18.0, "25d_call": 17.0},
                },
                "quant_metrics": {"volatility": {"expected_range": {"one_sigma": 10.0, "method": "TEST"}}},
                "order_flow": {"aggression": {"delta": 80.0, "price_displacement": 0.0}},
                "action_zones": {"setups": {
                    "breakout_retest_long": {"zone_price": 2315.0, "invalidation": 2280.0},
                    "breakout_retest_short": {"zone_price": 2280.0, "invalidation": 2315.0},
                }},
            },
            "order_flow": {"trades": [
                {"side": "BUY", "size": 100}, {"side": "BUY", "size": 105},
                {"side": "SELL", "size": 5}, {"side": "BUY", "size": 90},
                {"side": "SELL", "size": 3}, {"side": "BUY", "size": 110},
                {"side": "SELL", "size": 2}, {"side": "BUY", "size": 95},
                {"side": "SELL", "size": 1},
            ]},
        }
    }


def test_missing_modalities_stay_unknown():
    pack = build_evidence_fusion({"raw_series": {"market_state": {}}})
    assert pack["status"] == "DATA_INSUFFICIENT"
    assert pack["evidence"] == []


def test_three_sigma_is_first_class():
    pack = build_evidence_fusion(base_state())
    item = next(x for x in pack["evidence"] if x["evidence_id"] == "distribution.implied_3sd")
    assert item["value"]["low"] == 2270.0
    assert item["value"]["high"] == 2330.0


def test_tpo_and_extreme_form_relationship():
    state = base_state()
    state["raw_series"]["market_state"]["price"]["futures"] = 2330.0
    state["raw_series"]["market_state"]["price"]["cfd"] = 2329.5
    pack = build_evidence_fusion(state)
    assert "auction_distribution_extreme" in {x["relationship_id"] for x in pack["relationships"]}


def test_blocks_are_evidence_not_a_score():
    pack = build_evidence_fusion(base_state())
    blocks = next(x for x in pack["evidence"] if x["evidence_id"] == "flow.blocks")
    assert blocks["value"]["count"] >= 1
    assert "score" not in blocks["value"]


def test_smile_and_skew_are_present_without_directional_vote():
    pack = build_evidence_fusion(base_state())
    ids = {x["evidence_id"] for x in pack["evidence"]}
    assert "vol.smile" in ids
    conflict = next(x for x in pack["conflicts"] if x["conflict_id"] == "skew_is_risk_context")
    assert conflict["severity"] == "LOW"


def test_scenarios_keep_source_derived_levels():
    pack = build_evidence_fusion(base_state())
    long_case = next(x for x in pack["scenarios"] if x["side"] == "LONG")
    assert long_case["trigger"] == 2315.0
    assert long_case["invalidation"] == 2280.0
