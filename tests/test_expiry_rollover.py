from src.expiry_rollover import build_expiry_rollover_context, classify_expiry, expected_next_monthly_code


def snap(code, dte, rows):
    return {
        "dte": dte,
        "expiration_selection": {"selected": code},
        "raw_series": {"strike_rows": rows},
    }


def test_classifies_friday_and_monthly_series():
    assert classify_expiry("OG1X6")["is_friday"] is True
    assert classify_expiry("OGX6")["kind"] == "MONTHLY"
    assert classify_expiry("G1TX6")["weekday"] == "TUESDAY"


def test_friday_series_is_ranked_and_rollover_is_not_confirmed_from_one_snapshot():
    result = build_expiry_rollover_context([
        snap("OG1X6", 2.0, [
            {"strike": 4000, "oiCall": 100, "oiPut": 80},
            {"strike": 4050, "oiCall": 50, "oiPut": 20},
        ]),
        snap("OG2X6", 9.0, [
            {"strike": 4000, "oiCall": 120, "oiPut": 100},
            {"strike": 4050, "oiCall": 80, "oiPut": 40},
        ]),
    ], current_price=4025)

    assert result["friday_series"][0]["code"] == "OG1X6"
    assert result["friday_series"][1]["code"] == "OG2X6"
    assert result["rollover"]["friday"]["status"] == "CANDIDATE"
    assert result["rollover"]["confirmed"] is False
    assert result["rollover"]["friday"]["overlap_concentration"][0]["strike"] == 4000


def test_missing_next_series_stays_unknown_or_watch():
    result = build_expiry_rollover_context([
        snap("OGX6", 0.5, [{"strike": 4000, "oiCall": 100, "oiPut": 100}]),
    ])
    assert result["rollover"]["monthly"]["next_code"] is None
    assert result["rollover"]["monthly"]["status"] == "WATCH"


def test_oi_does_not_claim_aggressor_direction():
    result = build_expiry_rollover_context([
        snap("OG1X6", 2.0, [{"strike": 4000, "oiCall": 100, "oiPut": 100}]),
        snap("OG2X6", 9.0, [{"strike": 4000, "oiCall": 150, "oiPut": 150}]),
    ])
    assert "oi_does_not_identify_aggressor_side" in result["limitations"]


def test_next_monthly_code_is_calendar_only():
    assert expected_next_monthly_code("OGX6") == "OGZ6"
    assert expected_next_monthly_code("OGZ6") == "OGF7"
