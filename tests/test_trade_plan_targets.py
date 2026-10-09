from src.trade_plan_engine import build_trade_execution_plan


def test_all_routes_use_their_own_target_arrays_and_filter_invalid_tp_levels():
    state = {
        "price": {"cfd": 100.0},
        "market_map": {
            "long_reclaim_trigger": 110.0,
            "long_reclaim_stop": 105.0,
            "long_reclaim_trade_targets": [110.0, 120.0, 115.0, 120.0],
            "long_support_trigger": 90.0,
            "long_support_invalidation": 85.0,
            "long_support_trade_targets": [90.0, 100.0, 95.0],
            "short_rejection_trigger": 110.0,
            "short_rejection_stop": 115.0,
            "short_rejection_trade_targets": [110.0, 100.0, 105.0],
            "short_breakdown_trigger": 90.0,
            "short_breakdown_stop": 95.0,
            "short_breakdown_trade_targets": [90.0, 80.0, 85.0],
        },
        "decision": {"structural_bias": "BEARISH"},
        "technical": {
            "m15": {"trend": "bearish", "bos": "none"},
            "m5": {"trend": "bearish", "bos": "none"},
        },
    }

    plan = build_trade_execution_plan(state)

    assert plan["long_reclaim"]["targets"] == [115.0, 120.0]
    assert plan["long_support"]["targets"] == [95.0, 100.0]
    assert plan["short_rejection"]["targets"] == [105.0, 100.0]
    assert plan["short_breakdown"]["targets"] == [85.0, 80.0]

    for route in plan["routes"]:
        trigger = route["trigger"]
        targets = route["targets"]
        if trigger is None:
            continue
        assert all(target is None or target != trigger for target in targets)
