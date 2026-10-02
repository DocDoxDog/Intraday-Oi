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


def test_parser_resolves_product_without_fabricating_volume():
    raw = {
        "chart_data": {"strike_rows": [{"coords": "0,0,1,1", "templateid": "x", "fields": {"title": "4600 Strike", "oiPut": "10", "oiCall": "20", "oiTotal": "30"}}], "future_markers": ["Future: 4605"], "expected_ranges": []},
        "expiration_selection": {"selected": "G4RQ6", "dte_hint": 2.38},
        "page_heading": "Gold (OG|GC) G4RQ6 (2.38 DTE) vs 4605", "page_text": "", "screenshot": None,
    }
    result = parse(raw)
    assert result["product_symbol"] == "GC"
    assert result["put_volume"] is None
    assert result["call_volume"] is None


def test_secondary_oi_change_and_churn_image_map():
    from src.parser import _merge_secondary_views
    rows = [
        {"strike": 4200, "oiPut": 100, "oiCall": 120},
        {"strike": 4210, "oiPut": 50, "oiCall": 70},
    ]
    secondary = {
        "oi_change": {"rows": [
            {"strike": "4200", "fields": {"putChange": "12", "callChange": "-5"}},
            {"strike": "4210", "fields": {"putChange": "3"}},
        ]},
        "churn": {"rows": [
            {"strike": "4200", "fields": {"putChurn": "4", "callChurn": "2"}},
        ]},
    }
    merged, totals = _merge_secondary_views(rows, secondary)
    assert merged[0]["oiPutChange"] == 12
    assert merged[0]["oiCallChange"] == -5
    assert merged[1]["oiPutChange"] == 3
    assert totals["oi_change_put"] == 15
    assert totals["oi_change_call"] == -5
    assert totals["oi_change_total"] == 10
    assert merged[0]["churnPut"] == 4
    assert merged[0]["churnCall"] == 2
    assert totals["churn"] == 6
