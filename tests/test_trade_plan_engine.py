from src.trade_plan_engine import build_trade_execution_plan


def _state(price=4210.0):
    return {
        "price": {"cfd": price},
        "levels": {"resistance_current": 4200.0, "support_current": 4175.0,
                   "resistance_main": 4200.0, "support_main": 4175.0},
        "market_map": {"R1": 4230.0, "R2": 4250.0, "R3": 4270.0,
                       "S1": 4160.0, "S2": 4140.0, "S3": 4120.0},
        "decision_framework": {"steps": {"1_market_state": {"htf_structure": "bullish"}}},
        "technical": {
            "m15": {"trend": "bullish", "bos": "bullish", "momentum_5": 1},
            "m5": {"trend": "bullish", "bos": "bullish", "momentum_5": 1},
        },
    }


def test_long_becomes_confirmed_only_after_all_conditions():
    p = build_trade_execution_plan(_state())
    assert p["long"]["state"] == "CONFIRMED"
    assert p["state"] == "CONFIRMED"
    assert p["long"]["rr"][0] is not None


def test_touch_without_confirmation_stays_triggered():
    s = _state(price=4200.0)
    s["technical"]["m5"]["bos"] = None
    p = build_trade_execution_plan(s)
    assert p["long"]["state"] == "TRIGGERED_WAIT_CONFIRMATION"
    assert p["state"] == "TRIGGERED"


def test_below_trigger_is_armed():
    p = build_trade_execution_plan(_state(price=4190.0))
    assert p["long"]["state"] == "ARMED"
