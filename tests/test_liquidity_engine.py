from src.liquidity_engine import build_liquidity_context


def _state(structural="BEARISH", observed_at="2026-11-16T14:00:00+00:00"):
    return {
        "observed_at": observed_at,
        "price": {"cfd": 3858.2},
        "decision": {"structural_bias": structural},
        "technical": {
            "d1": {
                "prior_high": 4000.0,
                "prior_low": 3800.0,
                "sweep": "none",
                "fibonacci": {"swing_high": 4010.0, "swing_low": 3780.0},
            },
            "h4": {
                "prior_high": 3980.0,
                "prior_low": 3820.0,
                "sweep": "none",
                "fibonacci": {"swing_high": 3990.0, "swing_low": 3810.0},
            },
            "m15": {
                "prior_high": 3890.0,
                "prior_low": 3840.0,
                "sweep": "buy_side_sweep",
                "bos": "bearish_bos",
                "fibonacci": {"swing_high": 3895.0, "swing_low": 3835.0},
            },
            "m5": {
                "prior_high": 3885.0,
                "prior_low": 3845.0,
                "sweep": "none",
                "fibonacci": {"swing_high": 3890.0, "swing_low": 3840.0},
            },
        },
    }


def test_bearish_prefers_buy_side_sweep_and_external_downside():
    out = build_liquidity_context(_state())
    assert out["preferred_event"] == "BUY_SIDE_SWEEP"
    assert out["gate"] == "SWEEP_DETECTED"
    assert out["latest_preferred_sweep"]["timeframe"] == "m15"
    assert out["entry_rule"] == "SELL_AFTER_BUY_SIDE_SWEEP"
    assert out["external"]["short_targets"][0] == 3800.0


def test_bullish_waits_for_sell_side_sweep():
    state = _state(structural="BULLISH")
    out = build_liquidity_context(state)
    assert out["preferred_event"] == "SELL_SIDE_SWEEP"
    assert out["gate"] == "SWEEP_PENDING"
    assert out["entry_rule"] == "BUY_AFTER_SELL_SIDE_SWEEP"


def test_new_york_open_window_is_timezone_aware():
    state = _state(observed_at="2026-11-16T14:30:00+00:00")
    out = build_liquidity_context(state)
    assert out["session_window"]["name"] == "NEW_YORK_OPEN"
    assert out["session_window"]["active"] is True
