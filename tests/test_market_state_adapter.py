from src.market_state import attach_market_state


def test_legacy_adapter_marks_unresolved_state_as_incomplete():
    parsed = {
        "future_price": 4300,
        "vol": 25,
        "raw_series": {
            "strike_rows": [{"strike": 4300, "oiCall": 10, "oiPut": 5}],
            "totals": {
                "open_interest_total": 15,
                "oi_delta_put": 1,
                "oi_delta_call": 2,
            },
            "gex": {
                "status": "ok",
                "net_gex": 100,
                "gamma_flip": 4290,
                "call_wall": 4350,
                "put_wall": 4250,
                "calculation_version": "canonical-gex-v1",
                "gex_sign_convention": "DEALER_SHORT_PUBLIC",
                "gamma_source": "quikstrike",
            },
            "delta_exposure": {"net_delta_exposure": 12},
        },
    }
    result = attach_market_state(parsed)
    state = result["market_state"]
    assert state["symbol"] == "GC"
    assert state["gex"] == 100
    assert state["data_status"] == "INCOMPLETE"
    assert state["data_quality"] == 0.0
    assert "publication_time_unknown" in state["assumptions"]
    assert result["raw_series"]["market_state"] == state
