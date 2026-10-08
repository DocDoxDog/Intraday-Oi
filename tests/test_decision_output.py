from src.market_state import enrich_market_state, normalize_analyst_output


def _snapshot():
    return {
        "captured_at": "2026-10-02T13:00:00+00:00",
        "future_price": 4300,
        "vol": 20.0,
        "cfd_price": 4297,
        "basis_diff": 3,
        "observed_at": "2026-10-02T13:00:00+00:00",
        "technical_context": {
            "timeframes": {
                "h4": {"trend": "bearish"},
                "h1": {"trend": "bearish"},
                "m15": {"trend": "bearish"},
                "m5": {"trend": "bullish", "bos": "bullish"},
                "m1": {"trend": "bullish"},
            }
        },
        "raw_series": {
            "totals": {
                "open_interest_view_put": 120,
                "open_interest_view_call": 260,
                "open_interest_view_total": 380,
                "oi_delta_put": 10,
                "oi_delta_call": 20,
                "oi_delta_total": 30,
                "churn": 5,
            },
            "gex": {
                "net_gex": 1000,
                "call_wall": 4400,
                "put_wall": 4200,
                "gamma_flip": 4300,
                "rows": [
                    {"strike": 4150, "net_gex": -50},
                    {"strike": 4200, "net_gex": -100},
                    {"strike": 4250, "net_gex": 20},
                    {"strike": 4300, "net_gex": 30},
                    {"strike": 4400, "net_gex": 100},
                ],
            },
        },
    }


def test_llm_confirmation_cannot_override_deterministic_decision_state():
    parsed = enrich_market_state(_snapshot(), {})
    result = normalize_analyst_output(
        parsed,
        {},
        {
            "analysis_status": "CONFIRMED",
            "bias": "SELL",
            "trade_plan": {"status": "CONDITIONAL", "direction": "SELL"},
        },
    )

    assert result["structural_bias"] == "BEARISH"
    assert result["tactical_direction"] == "BULLISH_AGAINST_STRUCTURE"
    assert result["confirmation_state"] == "NOT_CONFIRMED"
    assert result["analysis_status"] == "DEVELOPING"
    assert result["bias"] == "BEARISH"
    assert result["trade_plan"]["direction"] == "WAIT"
