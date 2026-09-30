from src.gex import calculate_gex, black76_gamma


def test_black76_gamma_positive():
    gamma = black76_gamma(4300, 4300, 25.0, 3.0)
    assert gamma is not None
    assert gamma > 0


def test_gex_default_convention_is_explicit():
    result = calculate_gex(
        [{"strike": 4300, "gamma": 0.001, "oiCall": 100, "oiPut": 50}],
        4300,
        dte_days=3,
    )
    row = result["rows"][0]
    assert row["call_gex"] > 0
    assert row["put_gex"] < 0
    assert result["net_gex"] > 0
    assert result["call_wall"] == 4300
    assert result["put_wall"] == 4300
    assert result["dealer_position_observed"] is False
    assert result["gex_sign_convention"] if "gex_sign_convention" in result else result["convention"] == "DEALER_SHORT_PUBLIC"


def test_gex_alternative_sign_convention():
    result = calculate_gex(
        [{"strike": 4300, "gamma": 0.001, "oiCall": 100, "oiPut": 50}],
        4300,
        dte_days=3,
        convention="CALL_MINUS_PUT_PLUS",
    )
    row = result["rows"][0]
    assert row["call_gex"] < 0
    assert row["put_gex"] > 0
    assert result["net_gex"] < 0


def test_gex_gross_mode_is_non_directional():
    result = calculate_gex(
        [{"strike": 4300, "gamma": 0.001, "oiCall": 100, "oiPut": 50}],
        4300,
        dte_days=3,
        convention="GROSS_ABS",
    )
    assert result["positive_gamma"] is None
    assert result["net_gex"] > 0


def test_gex_derives_gamma_from_iv_when_missing():
    result = calculate_gex(
        [{"strike": 4300, "vol": 25.0, "oiCall": 100, "oiPut": 50}],
        4300,
        dte_days=3,
    )
    assert result["status"] == "ok"
    assert result["derived_gamma_count"] == 1
    assert result["rows"][0]["gamma_source"] == "black76_from_iv"
