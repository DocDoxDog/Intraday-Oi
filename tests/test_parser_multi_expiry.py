from src.parser import parse


def test_parser_preserves_multiple_expiration_identity():
    def raw(code, dte):
        return {
            "chart_data": {
                "strike_rows": [
                    {
                        "coords": "0,0,1,1",
                        "templateid": "x",
                        "fields": {
                            "title": f"4600 Strike",
                            "oiPut": "10",
                            "oiCall": "20",
                            "oiTotal": "30",
                            "gamma": "0.1",
                        },
                    }
                ],
                "future_markers": ["Future: 4605"],
                "expected_ranges": [],
            },
            "expiration_selection": {
                "selected": code,
                "dte_hint": dte,
            },
            "page_heading": f"Gold ({code}) ({dte} DTE) vs 4605",
            "page_text": "",
            "screenshot": None,
        }

    result = parse({
        "expiration_snapshots": [raw("OGU6", 1.38), raw("G4RQ6", 2.38)],
        **raw("OGU6", 1.38),
    })

    assert result["multi_expiration"]["count"] == 2
    assert [x["expiration_code"] for x in result["expiration_snapshots"]] == ["OGU6", "G4RQ6"]


def test_parser_keeps_real_source_screenshot():
    raw = {
        "chart_data": {
            "strike_rows": [{
                "coords": "0,0,1,1",
                "templateid": "x",
                "fields": {
                    "title": "4600 Strike",
                    "oiPut": "10",
                    "oiCall": "20",
                    "oiTotal": "30",
                },
            }],
            "future_markers": ["Future: 4605"],
            "expected_ranges": [],
        },
        "expiration_selection": {"selected": "OGU6", "dte_hint": 1.38},
        "page_heading": "Gold (OGU6) (1.38 DTE) vs 4605",
        "page_text": "",
        "screenshot": b"REAL-QUIKSTRIKE-SOURCE",
    }
    result = parse(raw)
    assert result["screenshot"] == b"REAL-QUIKSTRIKE-SOURCE"
