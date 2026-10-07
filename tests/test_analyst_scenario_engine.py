from src.analyst_scenario_engine import build_market_scenarios


def base_state():
    return {
        'price': {'cfd': 4142.0},
        'technical': {
            'h4': {'trend': 'bullish', 'swing_low': 4130.0},
            'h1': {'trend': 'bullish', 'swing_low': 4130.0},
            'm15': {'trend': 'bullish'},
            'm5': {'trend': 'bullish', 'bos': 'bullish'},
        },
        'decision_framework': {'steps': {'1_market_state': {'htf_structure': 'bullish'}}},
        'market_map': {
            'long_trigger': 4141.0,
            'short_trigger': 4076.0,
            'long_structural_levels': [4146.0, 4161.0, 4176.0],
            'short_structural_levels': [4060.0, 4040.0],
            'pivot': 4126.0,
        },
    }


def test_structural_levels_are_not_automatic_targets():
    long = build_market_scenarios(base_state())['scenarios']['long']
    assert long['structural_path'] == [4146.0, 4161.0, 4176.0]
    assert long['execution_targets'] == [4161.0, 4176.0]
    assert long['rr'] == [1.82, 3.18]


def test_gamma_context_is_not_a_target():
    result = build_market_scenarios(base_state())
    assert result['context']['gamma_mean'] == 4126.0
    assert 4126.0 not in result['scenarios']['long']['execution_targets']


def test_no_target_keeps_scenario_but_blocks_execution():
    state = base_state()
    state['technical']['h1']['swing_low'] = 4076.0
    state['technical']['h4']['swing_low'] = 4076.0
    long = build_market_scenarios(state)['scenarios']['long']
    assert long['execution_targets'] == []
    assert long['execution_eligible'] is False
    assert long['execution_block_reason'] == 'NO_TARGET_GE_1R'


def test_level_reached_is_not_confirmation():
    state = base_state()
    state['technical']['m5']['bos'] = 'bearish'
    result = build_market_scenarios(state)
    assert result['scenarios']['long']['status'] == 'LEVEL_REACHED_WAIT_CONFIRMATION'
    assert result['decision']['state'] == 'WAIT_CONFIRMATION'


def test_both_sides_armed_means_breakout_wait_not_no_trade():
    state = base_state()
    state['price']['cfd'] = 4100.0
    result = build_market_scenarios(state)
    assert result['decision']['state'] == 'RANGE_OR_BREAKOUT_WAIT'

def test_bearish_below_call_wall_prefers_retest_trigger_for_short():
    from src.market_state import _deterministic_trade_levels
    parsed = {
        "future_price": 4160.0,
        "cfd_price": 4132.24,
        "raw_series": {
            "gex": {
                "call_wall": 4165.0,
                "put_wall": 4185.0,
                "rows": [
                    {"strike": 4145.0, "oiTotal": 1000.0, "net_gex": -10.0},
                    {"strike": 4125.0, "oiTotal": 900.0, "net_gex": -9.0},
                    {"strike": 4105.0, "oiTotal": 800.0, "net_gex": -8.0},
                ],
            },
            "market_state": {
                "decision_framework": {
                    "steps": {"1_market_state": {"htf_structure": "bearish"}}
                }
            },
        },
    }
    levels = {"resistance_main": 4137.24, "support_main": 4157.24}
    plan = _deterministic_trade_levels(parsed, levels, parsed["raw_series"]["gex"])
    assert plan["short_trigger"] == 4137.24
    assert plan["short_stop"] == 4157.24
    assert plan["short_tp1"] == 4117.24
