"""Regression tests for the Gold Market Intelligence v1 engines."""
from src.auction import build_auction_profile
from src.order_flow import build_order_flow_context
from src.risk_engine import evaluate_setup_risk
from src.regime_engine import build_market_regime
from src.action_zone_engine import build_action_zones
from src.confirmation_engine import confirm_setup

def candles():
    return [
        {"datetime":"2026-10-07T01:00:00Z","open":4200,"high":4204,"low":4198,"close":4202,"volume":100},
        {"datetime":"2026-10-07T01:05:00Z","open":4202,"high":4205,"low":4200,"close":4204,"volume":200},
        {"datetime":"2026-10-07T01:10:00Z","open":4204,"high":4206,"low":4201,"close":4203,"volume":150},
        {"datetime":"2026-10-07T01:15:00Z","open":4203,"high":4204,"low":4199,"close":4200,"volume":250},
    ]

def base_state():
    return {
        "price":{"cfd":4200.0},
        "technical":{
            "h4":{"trend":"bearish"},
            "h1":{"trend":"bearish"},
            "m15":{"trend":"bearish"},
            "m5":{"trend":"bearish","bos":"bearish_bos","close":4199,"previous_close":4201,
                   "atr14":4.0,"sweep":"none"},
        },
        "levels":{"resistance_main":4210.0,"support_main":4190.0,
                  "resistance_current":4210.0,"support_current":4190.0},
        "market_map":{"long_trigger":4210.0,"short_trigger":4190.0,
                      "long_support_trigger":4190.0,
                      "long_invalidation":4205.0,"short_invalidation":4215.0},
        "auction":{"status":"OK","mode":"BAR_PROXY","bin_size":0.5,"poc":4200.0},
        "news":[],
        "order_flow":{"status":"UNKNOWN"},
    }

def test_auction_profile_is_bar_proxy_and_has_value_area():
    result = build_auction_profile(candles(), bin_size=0.5)
    assert result["status"] == "OK"
    assert result["mode"] == "BAR_PROXY"
    assert result["approximation"] == "CALENDAR_DAY_APPROX"
    assert result["poc"] is not None
    assert result["vah"] >= result["val"]

def test_order_flow_stays_unknown_without_source():
    result = build_order_flow_context()
    assert result["status"] == "UNKNOWN"
    assert result["availability"] == "NOT_PROVIDED"

def test_order_flow_classifies_explicit_aggressor_side():
    result = build_order_flow_context(
        trades=[
            {"aggressor_side":"BUY","price":4200,"size":3},
            {"aggressor_side":"SELL","price":4199.5,"size":1},
        ]
    )
    assert result["status"] == "OK"
    assert result["aggression"]["buy"] == 3
    assert result["aggression"]["sell"] == 1
    assert result["aggression"]["delta"] == 2

def test_risk_gate_rejects_stop_that_is_too_far_for_atr():
    result = evaluate_setup_risk(
        "LONG", 4200, 4180, [4220], atr=5.0, max_stop_atr=3.0
    )
    assert result["status"] == "NO_TRADE"
    assert result["reason"] == "STOP_TOO_FAR"

def test_risk_gate_rejects_missing_or_sub_1r_target():
    result = evaluate_setup_risk("LONG", 4200, 4195, [4204])
    assert result["status"] == "NO_TRADE"
    assert result["reason"] == "RR_BELOW_MIN"

def test_regime_is_trend_when_higher_timeframes_align():
    state = base_state()
    state["technical"]["h4"]["trend"] = "bullish"
    state["technical"]["h1"]["trend"] = "bullish"
    state["technical"]["m15"]["trend"] = "bullish"
    result = build_market_regime(state)
    assert result["regime"] == "TREND"
    assert result["bias"] == "BULLISH"

def test_action_zone_does_not_trigger_from_price_touch_alone():
    state = base_state()
    state["price"]["cfd"] = 4210.0
    state["technical"]["m5"]["bos"] = "none"
    result = build_action_zones(state)
    setup = result["setups"]["breakout_retest_long"]
    assert setup["state"] == "IN_ZONE"

def test_action_zone_can_detect_break_and_retest_proxy():
    state = base_state()
    state["technical"]["h4"]["trend"] = "bullish"
    state["technical"]["h1"]["trend"] = "bullish"
    state["technical"]["m15"]["trend"] = "bullish"
    state["technical"]["m5"].update({
        "trend":"bullish","bos":"bullish_bos","previous_close":4209.5,"close":4211.0
    })
    state["price"]["cfd"] = 4211.0
    result = build_action_zones(state)
    setup = result["setups"]["breakout_retest_long"]
    assert setup["state"] == "TRIGGERED"

def test_confirmation_requires_zone_event_and_lower_timeframe_structure():
    state = base_state()
    setup = {
        "setup_type":"BREAKOUT_RETEST","side":"SHORT","zone_price":4190,
        "state":"TRIGGERED","event_required":"breakdown + acceptance + retest failure"
    }
    result = confirm_setup(setup, state)
    assert result["state"] == "CONFIRMED"
    assert result["confirmed"] is True
