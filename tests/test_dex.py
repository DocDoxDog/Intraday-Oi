from quant.exposure.dex import calculate_dex


def test_dex_uses_canonical_multiplier():
    result = calculate_dex(
        [
            {
                "strike": 4300,
                "oiCall": 100,
                "oiPut": 50,
                "callDelta": 0.50,
                "putDelta": -0.50,
            }
        ],
        multiplier=100,
    )
    assert result["net_dex"] == 2500
    assert result["gross_dex"] == 7500
