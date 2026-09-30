import math

import pytest

from quant.greeks.black76 import calculate_black76_greeks, normalize_iv


def test_iv_percent_is_normalized_once():
    assert math.isclose(normalize_iv(25.0, "PERCENT"), 0.25)
    assert math.isclose(normalize_iv(0.25, "DECIMAL"), 0.25)


def test_call_put_delta_direction():
    call = calculate_black76_greeks(4300, 4300, 25.0, 30 / 365, "CALL", iv_unit="PERCENT")
    put = calculate_black76_greeks(4300, 4300, 25.0, 30 / 365, "PUT", iv_unit="PERCENT")
    assert call.delta > 0
    assert put.delta < 0
    assert call.gamma > 0
    assert math.isclose(call.gamma, put.gamma, rel_tol=1e-12)


def test_greeks_are_reproducible():
    a = calculate_black76_greeks(4300, 4400, 28.0, 7 / 365, "CALL", iv_unit="PERCENT")
    b = calculate_black76_greeks(4300, 4400, 28.0, 7 / 365, "CALL", iv_unit="PERCENT")
    assert a == b


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        calculate_black76_greeks(0, 4300, 25, 1 / 365, "CALL", iv_unit="PERCENT")
