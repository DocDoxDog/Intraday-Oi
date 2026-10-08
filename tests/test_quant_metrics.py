from src.quant_metrics import enrich_quant_metrics


def test_quant_metrics_basic_snapshot():
    parsed = {
        "future_price": 4201.5,
        "cfd_price": 4171.6,
        "basis_diff": 29.9,
        "dte": 0.2,
        "raw_series": {
            "market_state": {
                "flow": {
                    "oi_total": 2422,
                    "oi_put": 1098,
                    "oi_call": 1324,
                    "oi_change_put": 422,
                    "oi_change_call": 503,
                },
                "gamma": {
                    "net_gex": 116314106.11,
                    "call_wall": 4170.1,
                    "put_wall": 4145.1,
                },
                "volatility": {
                    "iv": 22.96,
                    "skew": 0.8,
                    "iv_term_structure": [
                        {"dte": 0.2, "iv": 22.96},
                        {"dte": 7.2, "iv": 21.0},
                    ],
                },
            }
        },
    }
    out = enrich_quant_metrics(
        parsed,
        {
            "hour_ago": {"future_price": 4195.0},
            "two_hours_ago": {"future_price": 4190.0},
            "today": {"future_price_open": 4180.0},
            "yesterday": {"future_price_last": 4175.0},
        },
    )
    q = out["raw_series"]["market_state"]["quant_metrics"]
    assert q["returns"]["1h"] is not None
    assert q["open_interest"]["call_put_ratio"] > 1
    assert q["gamma"]["interpretation"] == "POSITIVE_GAMMA_CONTEXT"
    assert "NEAR_EXPIRY" in q["risk_flags"]
    assert q["volatility"]["iv_term_slope_per_dte"] < 0


def test_quant_metrics_fail_closed_on_missing_data():
    out = enrich_quant_metrics({"raw_series": {"market_state": {}}}, {})
    q = out["raw_series"]["market_state"]["quant_metrics"]
    assert q["returns"]["1h"] is None
    assert q["open_interest"]["call_put_ratio"] is None
    assert q["gamma"]["interpretation"] == "UNKNOWN"


def test_expected_range_is_magnitude_only():
    parsed = {
        "future_price": 4000.0,
        "cfd_price": 3975.0,
        "basis_diff": 25.0,
        "vol": 36.5,
        "dte": 1.0,
        "raw_series": {"market_state": {"flow": {}, "gamma": {}, "volatility": {}}},
    }
    out = enrich_quant_metrics(parsed, {})
    er = out["raw_series"]["market_state"]["quant_metrics"]["volatility"]["expected_range"]
    assert er["one_sigma"] > 0
    assert er["two_sigma"] == er["one_sigma"] * 2
    assert er["direction"] == "UNKNOWN"


def test_expected_range_unknown_without_iv():
    parsed = {
        "future_price": 4000.0,
        "cfd_price": 3975.0,
        "dte": 1.0,
        "raw_series": {"market_state": {"flow": {}, "gamma": {}, "volatility": {}}},
    }
    out = enrich_quant_metrics(parsed, {})
    assert out["raw_series"]["market_state"]["quant_metrics"]["volatility"]["expected_range"] is None
