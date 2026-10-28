from src.multi_domain_engine import _technical_setup_candidates


def test_technical_candidates_are_source_derived_and_distinct():
    parsed = {
        "technical_context": {
            "ohlcv": {
                "m5": [
                    {"open": 100, "high": 103, "low": 99, "close": 102, "datetime": "2026-10-27T10:00:00Z"},
                    {"open": 102, "high": 104, "low": 101, "close": 103, "datetime": "2026-10-27T10:05:00Z"},
                ],
                "m15": [
                    {"open": 110, "high": 112, "low": 105, "close": 108, "datetime": "2026-10-27T10:00:00Z"},
                    {"open": 108, "high": 109, "low": 104, "close": 106, "datetime": "2026-10-27T10:15:00Z"},
                ],
                "h1": [
                    {"open": 100, "high": 115, "low": 95, "close": 110, "datetime": "2026-10-27T10:00:00Z"},
                ],
            }
        }
    }
    state = {
        "price": {"cfd": 105},
        "technical": {
            "m5": {
                "trend": "bullish",
                "fvg": {"side": "bullish", "low": 100, "high": 102},
                "prior_high": 110,
                "prior_low": 95,
                "fibonacci": {"swing_high": 115, "swing_low": 95, "retracement_62": 102.6, "retracement_79": 99.2},
            },
            "m15": {
                "trend": "bearish",
                "fvg": {"side": "bearish", "low": 108, "high": 110},
                "prior_high": 112,
                "prior_low": 104,
                "fibonacci": {"swing_high": 115, "swing_low": 100, "retracement_62": 105.7, "retracement_79": 103.15},
            },
            "h1": {
                "trend": "bullish",
                "fibonacci": {"swing_high": 115, "swing_low": 95, "retracement_62": 102.6, "retracement_79": 99.2},
                "prior_high": 115,
                "prior_low": 95,
            },
        },
    }
    rows = _technical_setup_candidates(state, parsed)
    assert len(rows) >= 3
    keys = {(x["side"], x["entry"], x["stop"], x["targets"][0]) for x in rows}
    assert len(keys) == len(rows)
    assert all(x["geometry_source"] == "OHLC_DERIVED" for x in rows)
    assert all(x["targets"] for x in rows)


def test_technical_candidates_reject_bad_geometry():
    parsed = {"technical_context": {"ohlcv": {"m5": [{"high": 101, "low": 99, "close": 100}]}}}
    state = {
        "price": {"cfd": 100},
        "technical": {
            "m5": {
                "trend": "bullish",
                "fvg": {"side": "bullish", "low": 102, "high": 103},
                "prior_high": 101,
                "prior_low": 99,
                "fibonacci": {"swing_high": 101, "swing_low": 99, "retracement_62": 99.76, "retracement_79": 99.42},
            }
        },
    }
    rows = _technical_setup_candidates(state, parsed)
    assert all(x["stop"] < x["entry"] < x["targets"][0] for x in rows if x["side"] == "LONG")
