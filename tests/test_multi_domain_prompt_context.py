from src.supabot_llm import _summarize_input


def test_summarize_input_carries_precomputed_multi_domain_evidence():
    parsed = {
        "raw_series": {
            "market_state": {
                "microeconomics": {
                    "status": "AVAILABLE",
                    "order_book": {"depth_bias": "BID_DEPTH_HEAVY"},
                }
            },
            "multi_domain": {
                "macro": {"regime": "GOLD_SUPPORTIVE"},
                "microeconomics": {
                    "status": "AVAILABLE",
                    "aggressor_flow": {"classification": "NET_AGGRESSIVE_BUYING"},
                },
                "psychology": {"mechanisms": ["liquidity_sweep"]},
                "strategy_candidates": [{"route": "FIB_OTE_LONG_M15", "score": 72.0}],
            },
        },
        "technical_context": {"timeframes": {}},
    }
    out = _summarize_input(parsed, {})
    evidence = out["current"]["raw_series"]["multi_domain"]
    assert evidence["macro"]["regime"] == "GOLD_SUPPORTIVE"
    assert evidence["microeconomics"]["aggressor_flow"]["classification"] == "NET_AGGRESSIVE_BUYING"
    assert evidence["strategy_candidates"][0]["route"] == "FIB_OTE_LONG_M15"
