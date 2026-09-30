from quant.exposure.gex import GEX_CALCULATION_VERSION, calculate_gex


def test_canonical_gex_has_one_version():
    result = calculate_gex(
        [
            {"strike": 4250, "gamma": 0.00110, "oiCall": 100, "oiPut": 50},
            {"strike": 4300, "gamma": 0.00100, "oiCall": 140, "oiPut": 160},
        ],
        4300,
        dte_days=3,
    )
    assert result["calculation_version"] == GEX_CALCULATION_VERSION
    assert result["gex_unit"] == "USD per 1% underlying move"
    assert result["dealer_position_observed"] is False


def test_gross_gex_is_absolute_call_plus_put_exposure():
    result = calculate_gex(
        [{"strike": 4300, "gamma": 0.001, "oiCall": 100, "oiPut": 100}],
        4300,
        dte_days=3,
    )
    row = result["rows"][0]
    assert result["gross_gex"] == abs(row["call_gex"]) + abs(row["put_gex"])


def test_zero_oi_and_zero_gamma_are_safe():
    result = calculate_gex(
        [
            {"strike": 4300, "gamma": 0.0, "oiCall": 100, "oiPut": 100},
            {"strike": 4350, "gamma": 0.001, "oiCall": 0, "oiPut": 0},
        ],
        4300,
        dte_days=3,
    )
    assert result["status"] == "ok"
    assert result["rows"][0]["net_gex"] == 0
    assert result["rows"][1]["net_gex"] == 0


def test_gross_mode_has_no_directional_walls():
    result = calculate_gex(
        [{"strike": 4300, "gamma": 0.001, "oiCall": 100, "oiPut": 50}],
        4300,
        dte_days=3,
        convention="GROSS_ABS",
    )
    assert result["positive_gamma"] is None
    assert result["call_wall"] is None
    assert result["put_wall"] is None


def test_gex_aggregates_multiple_expirations():
    result = calculate_gex(
        [
            {"strike": 4300, "gamma": 0.001, "oiCall": 100, "oiPut": 50, "expiration_id": "near"},
            {"strike": 4300, "gamma": 0.0008, "oiCall": 80, "oiPut": 40, "expiration_id": "far"},
        ],
        4300,
        multiplier=100,
    )
    assert result["expiry_count"] == 2
    assert set(result["gex_by_expiration"]) == {"near", "far"}
    assert result["net_gex"] == (
        result["gex_by_expiration"]["near"]["net_gex"]
        + result["gex_by_expiration"]["far"]["net_gex"]
    )
