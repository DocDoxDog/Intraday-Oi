from src.multi_domain_engine import build_quant_evidence, rank_trade_candidates, _microeconomics


def _bars(base: float, n: int = 60, spread: float = 1.0):
    rows = []
    for i in range(n):
        close = base - i * 0.1
        rows.append({
            "open": close + 0.05,
            "high": close + spread,
            "low": close - spread,
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
    # Same market area across horizons, with different observed ranges so the
    # resulting Fibonacci geometries are genuinely distinct and risk-valid.
    ohlcv = {tf: _bars(101.24, spread=0.5 + i * 0.25) for i, tf in enumerate(tfs)}
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



def test_microeconomics_uses_observed_aggressor_and_book_data_only():
    state = {
        "order_flow": {
            "status": "OK",
            "aggression": {
                "buy": 70.0, "sell": 30.0, "delta": 40.0,
                "total": 100.0, "trade_count": 20, "price_displacement": 0.25,
            },
            "book": {
                "status": "OK", "best_bid_depth": 120.0,
                "best_ask_depth": 80.0, "imbalance": 0.2, "spread": 0.1,
            },
            "hypotheses": [{"type": "ABSORPTION_CANDIDATE", "status": "CANDIDATE"}],
        }
    }
    out = _microeconomics(state)
    assert out["status"] == "AVAILABLE"
    assert out["aggressor_flow"]["classification"] == "NET_AGGRESSIVE_BUYING"
    assert out["order_book"]["depth_bias"] == "BID_DEPTH_HEAVY"
    assert out["price_impact"]["volume_per_price_unit_proxy"] == 400.0
    assert len(out["absorption_hypotheses"]) == 1


def test_microeconomics_stays_unknown_without_trade_or_book_observations():
    out = _microeconomics({})
    assert out["status"] == "UNKNOWN"
    assert out["aggressor_flow"]["classification"] == "UNKNOWN"
    assert out["order_book"]["depth_bias"] == "UNKNOWN"
    assert out["price_impact"]["volume_per_price_unit_proxy"] is None



def test_ranker_deduplicates_same_setup_across_strategy_labels():
    state = {
        "price": {"cfd": 100.0},
        "decision": {"structural_bias": "MIXED"},
        "technical": {},
        "market_map": {},
        "gamma": {},
    }
    execution = {
        "routes": [
            {"route": "FVG_M5", "side": "LONG", "trigger": 100, "stop": 98, "targets": [104, 106]},
            {"route": "FIB_M15", "side": "LONG", "trigger": 100, "stop": 98, "targets": [104, 108]},
            {"route": "BOS_H1", "side": "LONG", "trigger": 101, "stop": 98, "targets": [104]},
        ]
    }
    rows = rank_trade_candidates(state, execution, {"technical_context": {"ohlcv": {}}})
    assert len(rows) == 2
    assert {(x["side"], x["entry"], x["stop"], x["targets"][0]) for x in rows} == {
        ("LONG", 100.0, 98.0, 104.0),
        ("LONG", 101.0, 98.0, 104.0),
    }
