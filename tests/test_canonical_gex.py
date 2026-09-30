from math import isclose

from quant.exposure.gex import GEX_CALCULATION_VERSION, calculate_gex, calculate_gex_result


def sample_rows():
    return [
        {"strike": 4250, "gamma": 0.00110, "oiCall": 100, "oiPut": 50},
        {"strike": 4300, "gamma": 0.00100, "oiCall": 140, "oiPut": 160},
        {"strike": 4350, "gamma": 0.00090, "oiCall": 60, "oiPut": 120},
    ]


def test_canonical_gex_has_one_version():
    result = calculate_gex(sample_rows(), 4300, dte_days=3)
    assert result["calculation_version"] == GEX_CALCULATION_VERSION
    assert result["gex_unit"] == "USD per 1% underlying move"
    assert result["dealer_position_observed"] is False


def test_canonical_gex_zero_oi_and_zero_gamma_are_safe():
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


def test_canonical_gex_can_derive_gamma_from_iv():
    result = calculate_gex(
        [{"strike": 4300, "vol": 25.0, "oiCall": 100, "oiPut": 50}],
        4300,
        dte_days=3,
    )
    assert result["derived_gamma_count"] == 1
    assert result["rows"][0]["gamma_source"] == "BLACK76_FROM_IV"


def test_wrapper_path_is_same_engine():
    from src.gex import calculate_gex as legacy_path

    a = calculate_gex(sample_rows(), 4300, dte_days=3)
    b = legacy_path(sample_rows(), 4300, dte_days=3)
    assert a == b
