from src.parser import parse


def test_expected_ranges_survive_parser():
    raw = {
        "chart_data": {
            "strike_rows": [
                {"fields": {"title": "3000 Strike", "oiPut": "100", "oiCall": "80"}},
            ],
            "expected_ranges": [
                {"name": "One", "lower": 2990, "upper": 3010},
                {"name": "Two", "lower": 2980, "upper": 3020},
            ],
            "future_markers": [],
        },
        "page_heading": "Gold (3 DTE) vs 3000",
        "page_text": "",
        "expiration_selection": {"selected": "OG...", "dte_hint": 3.0},
    }
    parsed = parse(raw)
    ranges = parsed["raw_series"]["expected_ranges"]
    assert ranges[0]["name"] == "One"
    assert ranges[0]["lower"] == 2990
    assert ranges[1]["upper"] == 3020
