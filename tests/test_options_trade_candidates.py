from src.multi_domain_engine import _options_setup_candidates


def test_options_max_pain_candidate_uses_cfd_basis():
    state = {
        "price": {"cfd": 4020, "basis": 20},
        "quant": {
            "options_surface": {
                "status": "AVAILABLE",
                "max_pain": {"strike": 4050},
            }
        },
        "market_map": {
            "local_action_support": 4015,
            "local_action_resistance": 4070,
        },
    }
    rows = _options_setup_candidates(state)
    assert rows
    assert rows[0]["side"] == "LONG"
    assert rows[0]["entry"] == 4020
    assert rows[0]["targets"] == [4030]
    assert rows[0]["stop"] == 4015
