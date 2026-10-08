from src.trade_plan_engine import build_trade_execution_plan


def test_countertrend_confirmation_cannot_be_global_confirmation():
    state = {
        "price": {"cfd": 4200.0},
        "levels": {"resistance_current": 4200.0, "support_current": 4175.0,
                   "resistance_main": 4200.0, "support_main": 4175.0},
        "market_map": {
            "long_reclaim_trigger": 4200.0, "long_reclaim_stop": 4175.0,
            "long_reclaim_tp1": 4230.0,
            "long_support_trigger": 4175.0, "long_support_invalidation": 4140.0,
            "long_support_tp1": 4230.0,
            "short_rejection_trigger": 4200.0, "short_rejection_stop": 4205.0,
            "short_rejection_tp1": 4160.0,
            "short_breakdown_trigger": 4175.0, "short_breakdown_stop": 4180.0,
            "short_breakdown_tp1": 4160.0,
        },
        "decision": {"structural_bias": "BEARISH"},
        "decision_framework": {
            "steps": {"1_market_state": {"htf_structure": "bearish"}}
        },
        "technical": {
            "m15": {"trend": "bullish", "bos": "bullish", "momentum_5": 1},
            "m5": {"trend": "bullish", "bos": "bullish", "momentum_5": 1},
        },
        "action_zones": {
            "setups": {
                "breakout_retest_long": {
                    "setup_type": "BREAKOUT_RETEST",
                    "side": "LONG",
                    "zone_price": 4200.0,
                    "state": "TRIGGERED",
                    "event_required": "breakout + acceptance proxy + retest hold",
                },
                "reversal_long": {
                    "setup_type": "REVERSAL",
                    "side": "LONG_SUPPORT",
                    "zone_price": 4175.0,
                    "state": "WAIT",
                    "event_required": "support interaction + rejection + bullish BOS",
                },
                "reversal_short": {
                    "setup_type": "REVERSAL",
                    "side": "SHORT",
                    "zone_price": 4200.0,
                    "state": "WAIT",
                    "event_required": "resistance interaction + rejection + bearish BOS",
                },
                "breakout_retest_short": {
                    "setup_type": "BREAKOUT_RETEST",
                    "side": "SHORT",
                    "zone_price": 4175.0,
                    "state": "WAIT",
                    "event_required": "breakdown + acceptance proxy + retest failure",
                },
            }
        },
        "order_flow": {"status": "UNKNOWN"},
    }

    plan = build_trade_execution_plan(state)

    assert plan["long"]["state"] == "COUNTERTREND_CONFIRMED"
    assert plan["state"] == "COUNTERTREND_ROUTE_CONFIRMED"
    assert plan["preferred_setup"] is None
