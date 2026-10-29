from src.quant_metrics import _options_surface


def test_options_surface_max_pain_and_moneyness():
    rows = [
        {"strike": 3990, "oiCall": 100, "oiPut": 500, "vol": 25},
        {"strike": 4000, "oiCall": 300, "oiPut": 400, "vol": 24},
        {"strike": 4010, "oiCall": 500, "oiPut": 200, "vol": 23},
        {"strike": 4020, "oiCall": 200, "oiPut": 100, "vol": 24},
    ]
    out = _options_surface(rows, 4007)
    assert out["status"] == "AVAILABLE"
    assert out["atm"]["strike"] == 4010
    assert out["max_pain"]["strike"] in {4000, 4010}
    assert out["moneyness_oi"]["call"]["ITM"] > 0
    assert out["moneyness_oi"]["put"]["OTM"] > 0
    assert out["iv_skew"]["status"] == "CURVE_ONLY"


def test_options_surface_explicit_call_put_skew():
    rows = [
        {"strike": 3990, "oiCall": 100, "oiPut": 500, "vol": 30, "callIV": 28, "putIV": 35},
        {"strike": 4000, "oiCall": 300, "oiPut": 400, "vol": 27, "callIV": 27, "putIV": 31},
        {"strike": 4010, "oiCall": 500, "oiPut": 200, "vol": 26, "callIV": 26, "putIV": 26},
        {"strike": 4020, "oiCall": 200, "oiPut": 100, "vol": 28, "callIV": 29, "putIV": 25},
    ]
    out = _options_surface(rows, 4007)
    skew = out["iv_skew"]
    assert skew["status"] == "AVAILABLE"
    assert skew["risk_reversal_put_minus_call"] > 0
