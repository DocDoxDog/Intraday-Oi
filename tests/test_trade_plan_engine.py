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


def test_structural_key_levels_are_not_automatic_trade_targets():
    state = _state(price=4140.0)
    state["levels"] = {
        "resistance_current": 4141.33,
        "support_current": 4076.33,
        "resistance_main": 4141.33,
        "support_main": 4076.33,
    }
    state["market_map"] = {
        "R1": 4146.33, "R2": 4161.33, "R3": 4176.33,
        "S1": None, "S2": None, "S3": None,
        "long_trade_targets": [],
        "short_trade_targets": [],
    }
    p = build_trade_execution_plan(state)
    assert p["long"]["targets"] == []
    assert p["long"]["rr"][0] is None
    assert p["long"]["state"] in {"ARMED", "TRIGGERED_WAIT_RISK_REWARD", "TRIGGERED_WAIT_CONFIRMATION"}
