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


def test_dex_aggregates_expiration_buckets():
    result = calculate_dex(
        [
            {"expiration_id": "near", "oiCall": 10, "oiPut": 5, "callDelta": 0.5, "putDelta": -0.5},
            {"expiration_id": "far", "oiCall": 20, "oiPut": 10, "callDelta": 0.4, "putDelta": -0.4},
        ],
        multiplier=100,
    )
    assert result["expiry_count"] == 2
    assert result["net_dex"] == sum(x["net_dex"] for x in result["dex_by_expiration"].values())
