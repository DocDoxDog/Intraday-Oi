from src.decision_engine import build_decision_context


def _state(h4="bearish", h1="bearish", m15="bearish", m5="bearish", bos="bearish",
           price=4090, resistance=4140, support=4100, net_gex=100.0, iv_change=-1.0):
    return {
        "price": {"cfd": price, "dte": 0.39},
        "levels": {
            "resistance_current": resistance,
            "support_current": support,
        },
        "technical": {
            "h4": {"trend": h4},
            "h1": {"trend": h1},
            "m15": {"trend": m15},
            "m5": {"trend": m5, "bos": bos},
            "m1": {"trend": m5},
        },
        "flow": {
            "oi_change_put": 100,
            "oi_change_call": 80,
        },
        "volatility": {
            "iv": 28.49,
            "iv_change_1h": iv_change,
            "iv_term_structure": [],
        },
        "gamma": {
            "net_gex": net_gex,
        },
        "news": [],
        "regime": {"regime": "TREND"},
        "history": {},
    }


def test_mixed_tactical_recovery_cannot_become_confirmed_bearish():
    state = _state(h4="bearish", h1="bearish", m15="bearish", m5="bullish",
                   bos="bullish", price=4127)
    out = build_decision_context(state)

    assert out["structural_bias"] == "BEARISH"
    assert out["tactical_direction"] == "BULLISH_AGAINST_STRUCTURE"
    assert out["confirmation_state"] == "NOT_CONFIRMED"
    assert out["decision_state"] == "WAIT_BEARISH"
    assert out["analysis_status"] == "DEVELOPING"
    assert out["confirmation"]["SHORT"]["confirmed"] is False
    assert out["options_context"]["gamma"] == "POSITIVE_GAMMA_DAMPENING_CONTEXT"


def test_mixed_higher_timeframe_structure_resolves_to_wait_transition():
    state = _state(h4="bearish", h1="bullish", m15="bullish", m5="bullish",
                   bos="bullish", price=4127)
    out = build_decision_context(state)

    assert out["structural_bias"] == "MIXED"
    assert out["decision_state"] == "WAIT_TRANSITION"
    assert out["confirmation_state"] == "NOT_CONFIRMED"
    assert out["analysis_status"] == "DEVELOPING"
    assert "H4/H1 ไม่สอดคล้องกัน" in out["conflicts"]


def test_price_and_structure_confirmation_are_required_for_confirmed_short():
    state = _state(h4="bearish", h1="bearish", m15="bearish", m5="bearish",
                   bos="bearish", price=4090, support=4100)
    out = build_decision_context(state)

    assert out["structural_bias"] == "BEARISH"
    assert out["confirmation"]["SHORT"]["confirmed"] is True
    assert out["confirmation_state"] == "CONFIRMED"
    assert out["decision_state"] == "BEARISH_CONFIRMED"
    assert out["analysis_status"] == "CONFIRMED"


def test_positive_gamma_is_context_not_a_range_prediction():
    state = _state(net_gex=10.0, price=4127)
    out = build_decision_context(state)

    assert out["options_context"]["gamma"] == "POSITIVE_GAMMA_DAMPENING_CONTEXT"
    assert "กรอบราคา" in " ".join(out["conflicts"])
    assert "range" not in out["summary"].lower()


def test_iv_level_never_claimed_high_without_baseline():
    state = _state()
    out = build_decision_context(state)

    assert out["options_context"]["volatility"]["level_assessment"] == "CURRENT_ONLY_BASELINE_UNAVAILABLE"
    assert "high" not in out["summary"].lower()
    assert "low" not in out["summary"].lower()
