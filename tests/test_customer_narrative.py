from src.customer_narrative import build_customer_narrative


def _fixture():
    return {
        "cfd_price": 4350.0,
        "future_price": 4352.0,
        "dte": 0.8,
        "raw_series": {
            "market_state": {
                "decision": {
                    "structural_bias": "BULLISH",
                    "tactical_direction": "BULLISH",
                    "confirmation_state": "NOT_CONFIRMED",
                },
                "regime": {"regime": "TREND_UP"},
                "price": {"cfd": 4350.0, "futures": 4352.0, "dte": 0.8},
                "gamma": {
                    "net_gex": -120.0,
                    "call_wall": 4370.0,
                    "put_wall": 4315.0,
                },
                "volatility": {
                    "iv": 18.2,
                    "iv_change_1h": 0.7,
                    "iv_term_structure": [],
                },
                "flow": {
                    "oi_change_put": 1200,
                    "oi_change_call": 900,
                    "source_churn_total": 3.5,
                },
                "history": {
                    "1h": {"price": 8.0, "vol": 0.4, "gex": -15.0}
                },
                "technical": {
                    "h4": {"trend": "bullish"},
                    "h1": {"trend": "bullish"},
                    "m15": {"trend": "bullish"},
                    "m5": {"trend": "bullish"},
                },
            },
            "market_flow": {
                "path": {
                    "current_price": 4350.0,
                    "upper_node": {"level": 4370.0, "role": "CALL_WALL"},
                    "lower_node": {"level": 4315.0, "role": "PUT_WALL"},
                    "next_up": {"level": 4390.0},
                    "next_down": {"level": 4290.0},
                }
            },
            "evidence_fusion_v52": {"conflicts": []},
        },
    }


def test_summary_reads_like_one_story():
    result = build_customer_narrative(_fixture(), {})
    summary = result["summary"]

    assert summary
    assert "|" not in summary
    assert "ตอนนี้" in summary
    assert "ถ้า" in summary
    assert summary.count("ผู้เล่น") == 0
    assert summary.count("dealer") == 0
    assert len(summary.split(" ")) < 120


def test_supporting_sections_do_not_become_metric_dumps():
    result = build_customer_narrative(_fixture(), {})

    assert "|" not in result["flow_statement"]
    assert "|" not in result["volatility"]
    assert "|" not in result["history"]
    assert "ยังไม่" in result["invalidation"] or "มุมมอง" in result["invalidation"]


def test_missing_evidence_stays_unknown_without_fabrication():
    parsed = {
        "raw_series": {
            "market_state": {
                "decision": {
                    "structural_bias": "MIXED",
                    "tactical_direction": "NEUTRAL",
                    "confirmation_state": "NOT_CONFIRMED",
                },
                "regime": {"regime": "UNKNOWN"},
            }
        }
    }

    result = build_customer_narrative(parsed, {})
    assert result["summary"]
    assert "ยัง" in result["summary"]
