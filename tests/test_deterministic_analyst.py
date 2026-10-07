from src.deterministic_analyst import build_deterministic_fallback


def test_fallback_is_conditional_and_not_raw_dump():
    parsed = {
        "future_price": 4201.5,
        "cfd_price": 4171.6,
        "basis_diff": 29.9,
        "dte": 0.2,
        "vol": 22.96,
        "technical_context": {
            "timeframes": {
                "h4": {"trend": "bearish"},
                "h1": {"trend": "bullish"},
                "m15": {"trend": "bearish"},
                "m5": {"trend": "bearish"},
            }
        },
        "raw_series": {
            "totals": {
                "open_interest_put": 1098,
                "open_interest_call": 1324,
                "oi_change_put": 422,
                "oi_change_call": 503,
                "churn": 27.22,
            },
            "gex": {
                "net_gex": 116314106.11,
                "call_wall": 4170.1,
                "put_wall": 4145.1,
            },
            "market_state": {
                "flow": {
                    "oi_put": 1098,
                    "oi_call": 1324,
                    "oi_change_put": 422,
                    "oi_change_call": 503,
                    "source_churn_total": 27.22,
                },
                "gamma": {
                    "net_gex": 116314106.11,
                    "call_wall": 4170.1,
                    "put_wall": 4145.1,
                },
                "decision_framework": {
                    "steps": {"8_decision": "WAIT_MIXED_STRUCTURE"}
                },
            },
        },
        "news_context": [],
    }
    out = build_deterministic_fallback(parsed, {}, error="LLM_VERIFICATION_FAILED")
    assert out["analysis_status"] == "DEGRADED"
    assert out["bias"] == "WAIT"
    assert out["trade_plan"]["status"] == "CONDITIONAL"
    assert "OI activity" in out["why"]
    assert "dealer" in out["market_psychology"]
    assert "raw metrics" not in out["market_overview"]
    assert out["evidence_refs"] == ["itb:oi:deterministic", "itb:oi:history"]
