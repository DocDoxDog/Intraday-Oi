from src.multi_expiry import build_gamma_matrix, summarize_gamma_zones


def snapshot(code, dte, rows, observed_at="2026-10-02T06:00:00+00:00"):
    return {
        "expiration_code": code,
        "dte": dte,
        "observed_at": observed_at,
        "raw_series": {"strike_rows": rows},
    }


def test_multi_expiry_keeps_real_expiration_identity():
    result = build_gamma_matrix([
        snapshot("OGU6", 1.38, [{"strike": 4600, "net_gex": 10}]),
        snapshot("G4RQ6", 2.38, [{"strike": 4600, "net_gex": -4}]),
    ])
    assert result["expiration_count"] == 2
    assert [x["code"] for x in result["columns"]] == ["OGU6", "G4RQ6"]
    assert result["matrix"] == [
        {"strike": 4600.0, "OGU6": 10.0, "G4RQ6": -4.0}
    ]


def test_missing_cell_is_unknown_not_zero():
    result = build_gamma_matrix([
        snapshot("OGU6", 1.38, [{"strike": 4600, "net_gex": 10}]),
        snapshot("G4RQ6", 2.38, [{"strike": 4610, "net_gex": 5}]),
    ])
    assert result["matrix"] == [
        {"strike": 4600.0, "OGU6": 10.0, "G4RQ6": None},
        {"strike": 4610.0, "OGU6": None, "G4RQ6": 5.0},
    ]


def test_zone_summary_is_deterministic():
    result = build_gamma_matrix([
        snapshot("OGU6", 1.0, [
            {"strike": 4600, "net_gex": 100},
            {"strike": 4610, "net_gex": -20},
        ]),
        snapshot("G4RQ6", 2.0, [
            {"strike": 4600, "net_gex": 10},
            {"strike": 4610, "net_gex": -50},
        ]),
    ], current_price=4605)
    zones = summarize_gamma_zones(result)
    assert zones["highest_positive_gamma"] == 4600
    assert zones["highest_negative_gamma"] == 4610


def test_empty_expiration_total_is_unknown_not_zero():
    result = build_gamma_matrix([snapshot("OGU6", 1.0, [{"strike": 4600, "net_gex": None}])])
    assert result["totals"]["OGU6"] is None
