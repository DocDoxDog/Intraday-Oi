from src.market_state import _deterministic_trade_levels, _validate_or_clear_trade_plan


def test_trade_map_uses_structural_walls_and_non_adjacent_source_strikes():
    parsed = {
        "future_price": 4162.30,
        "cfd_price": 4137.51,
        "raw_series": {
            "gex": {
                "call_wall": 4165.21,
                "put_wall": 4125.21,
                "rows": [
                    {"strike": 4170, "oiTotal": 100, "net_gex": 1},
                    {"strike": 4180, "oiTotal": 900, "net_gex": 10},
                    {"strike": 4200, "oiTotal": 800, "net_gex": 8},
                    {"strike": 4220, "oiTotal": 700, "net_gex": 7},
                    {"strike": 4115, "oiTotal": 100, "net_gex": 1},
                    {"strike": 4100, "oiTotal": 900, "net_gex": 10},
                    {"strike": 4080, "oiTotal": 800, "net_gex": 8},
                    {"strike": 4060, "oiTotal": 700, "net_gex": 7},
                ],
            }
        },
    }
    levels = {
        "resistance_main": 4140.42,
        "support_main": 4100.42,
    }
    plan = _deterministic_trade_levels(parsed, levels, {})
    assert plan["long_trigger"] == 4140.42
    assert plan["short_trigger"] == 4100.42
    assert plan["long_tp1"] in {4145.21, 4155.21, 4175.21}
    assert plan["short_tp1"] in {4090.42, 4075.42, 4055.42}
    assert plan["long_tp1"] != 4145.21 or plan["long_tp2"] is None or abs(plan["long_tp2"] - plan["long_tp1"]) >= 15
    assert plan["short_tp1"] != 4090.42 or plan["short_tp2"] is None or abs(plan["short_tp1"] - plan["short_tp2"]) >= 15
    assert 4139.85 not in {
        plan["long_tp1"], plan["long_tp2"], plan["long_tp3"],
        plan["short_tp1"], plan["short_tp2"], plan["short_tp3"],
    }


def test_trade_validation_keeps_valid_side_when_other_side_is_incomplete():
    plan = {
        "long_trigger": 4140,
        "long_stop": 4100,
        "long_tp1": 4155,
        "long_tp2": 4175,
        "long_tp3": 4200,
        "short_trigger": 4100,
        "short_stop": 4140,
        "short_tp1": None,
        "short_tp2": None,
        "short_tp3": None,
        "status": "CONDITIONAL",
        "direction": "WAIT",
    }
    out = _validate_or_clear_trade_plan(plan)
    assert out["long_status"] == "CONDITIONAL"
    assert out["short_status"] == "NO_TRADE"
    assert out["long_tp3"] == 4200
    assert out["short_trigger"] is None
    assert out["status"] == "CONDITIONAL"
