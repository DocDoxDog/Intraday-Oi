from src.customer_narrative import build_customer_narrative


def test_market_read_uses_deterministic_decision_not_llm_status():
    parsed = {
        "raw_series": {
            "market_state": {
                "decision": {
                    "structural_bias": "BEARISH",
                    "tactical_direction": "BULLISH_AGAINST_STRUCTURE",
                    "confirmation_state": "NOT_CONFIRMED",
                    "decision_state": "WAIT_BEARISH",
                },
                "flow": {},
                "volatility": {},
                "technical": {"h4": {"trend": "bearish"}, "h1": {"trend": "bearish"}},
            }
        }
    }
    out = build_customer_narrative(
        parsed,
        {
            "analysis_status": "CONFIRMED",
            "market_overview": "confirmed sell setup",
            "bias": "SELL",
        },
    )
    assert "ภาพหลักยังเป็นขาลง" in out["market_read"]
    assert "ฟื้นตัวระยะสั้น" in out["market_read"]
    assert "confirmed sell" not in out["market_read"].lower()
