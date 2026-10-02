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
