from src.multi_domain_engine import build_quant_evidence, rank_trade_candidates


def _bars(base: float, n: int = 60):
    rows = []
    for i in range(n):
        close = base - i * 0.1
        rows.append({
            "open": close + 0.05,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "datetime": f"2026-10-30T00:{i:02d}:00+00:00",
        })
    return rows


def test_quant_engine_consumes_m30_ohlcv():
    parsed = {
        "technical_context": {
            "ohlcv": {"m30": _bars(120.0)},
        }
    }
    out = build_quant_evidence(parsed)
    assert "m30" in out["timeframes"]
    assert out["timeframes"]["m30"]["atr14"] is not None


def test_ranker_can_return_five_distinct_ohlc_setups():
    tfs = ("d1", "h4", "h1", "m30", "m15", "m5")
    ohlcv = {tf: _bars(120.0 + i * 2.0) for i, tf in enumerate(tfs)}
    state = {
        "price": {"cfd": 100.0},
        "decision": {"structural_bias": "BEARISH"},
        "technical": {tf: {"trend": "bearish"} for tf in tfs},
        "market_map": {},
        "gamma": {"net_gex": 100.0},
    }
    parsed = {"technical_context": {"ohlcv": ohlcv}}
    candidates = rank_trade_candidates(state, {"routes": []}, parsed)
    assert len(candidates) >= 5
    assert len({c["route"] for c in candidates[:5]}) == 5
    assert all(c["side"] == "SHORT" for c in candidates[:5])
