from src.market_state import enrich_market_state, normalize_analyst_output


def _snapshot(captured_at, future, put, call, gex=-100.0, vol=20.0):
    return {
        "captured_at": captured_at,
        "future_price": future,
        "vol": vol,
        "raw_series": {
            "totals": {
                "open_interest_view_put": put,
                "open_interest_view_call": call,
                "open_interest_view_total": put + call,
                "oi_delta_put": 10,
                "oi_delta_call": 20,
                "oi_delta_total": 30,
                "churn": 5,
            },
            "gex": {
                "net_gex": gex,
                "call_wall": 4400,
                "put_wall": 4200,
                "gamma_flip": 4300,
                "call_gex_total": 1000,
                "put_gex_total": -1100,
                "rows": [
                    {"strike": 4150, "net_gex": -50},
                    {"strike": 4200, "net_gex": -100},
                    {"strike": 4250, "net_gex": 20},
                    {"strike": 4300, "net_gex": 30},
                    {"strike": 4400, "net_gex": 100},
                    {"strike": 4500, "net_gex": 80},
                ],
            },
        },
    }


def test_cfd_levels_are_normalized_from_futures():
    parsed = _snapshot("2026-10-02T13:00:00+00:00", 4300, 100, 200)
    parsed.update({"cfd_price": 4297, "basis_diff": 3, "observed_at": "2026-10-02T13:00:00+00:00"})
    enrich_market_state(parsed, {})
    levels = parsed["raw_series"]["market_state"]["levels"]
    assert levels["resistance_main"] == 4397
    assert levels["support_main"] == 4197
    assert levels["resistance_current"] == 4397


def test_missing_cfd_never_reuses_futures_levels():
    parsed = _snapshot("2026-10-02T13:00:00+00:00", 4300, 100, 200)
    parsed.update({"cfd_price": None, "basis_diff": None, "observed_at": "2026-10-02T13:00:00+00:00"})
    enrich_market_state(parsed, {})
    levels = parsed["raw_series"]["market_state"]["levels"]
    assert all(value is None for value in levels.values())


def test_flow_ratios_velocity_and_acceleration_are_deterministic():
    parsed = _snapshot("2026-10-02T13:00:00+00:00", 4300, 120, 260, gex=-80)
    parsed.update({"cfd_price": 4297, "basis_diff": 3, "observed_at": "2026-10-02T13:00:00+00:00"})
    hour = _snapshot("2026-10-02T12:00:00+00:00", 4290, 100, 220, gex=-120)
    two = _snapshot("2026-10-02T11:00:00+00:00", 4280, 90, 210, gex=-140)
    parsed = enrich_market_state(parsed, {"hour_ago": hour, "two_hours_ago": two})
    flow = parsed["raw_series"]["market_state"]["flow"]
    assert flow["call_put_oi_ratio"] == round(260 / 120, 6)
    assert flow["oi_velocity_per_hour"]["total"] == 60
    assert flow["oi_acceleration_per_hour2"]["total"] == 40


def test_history_summary_always_covers_three_horizons():
    parsed = _snapshot("2026-10-02T13:00:00+00:00", 4300, 120, 260)
    parsed.update({"cfd_price": 4297, "basis_diff": 3, "observed_at": "2026-10-02T13:00:00+00:00"})
    history = {
        "hour_ago": _snapshot("2026-10-02T12:00:00+00:00", 4290, 100, 220),
        "today": {
            "count": 3,
            "future_price_open": 4270,
            "vol_first": 19,
            "oi_first": {"oi_put": 90, "oi_call": 190, "oi_total": 280, "churn": 2, "gex_net": -50},
        },
        "yesterday": {
            "count": 5,
            "future_price_last": 4250,
            "vol_last": 18,
            "oi_last": {"oi_put": 80, "oi_call": 180, "oi_total": 260, "churn": 3, "gex_net": -20},
        },
    }
    parsed = enrich_market_state(parsed, history)
    summary = parsed["raw_series"]["market_state"]["history"]["summary"]
    assert "1H:" in summary
    assert "TODAY:" in summary
    assert "YESTERDAY:" in summary


def test_trade_plan_is_always_conditional_and_deterministic_when_levels_exist():
    parsed = _snapshot("2026-10-02T13:00:00+00:00", 4300, 100, 200)
    parsed.update({"cfd_price": 4297, "basis_diff": 3, "observed_at": "2026-10-02T13:00:00+00:00"})
    enrich_market_state(parsed, {})
    ai = normalize_analyst_output(
        parsed,
        {},
        {"analysis_status": "CONFIRMED", "bias": "WAIT", "trade_plan": {"status": "NO_TRADE"}},
    )
    trade = ai["trade_plan"]
    assert trade["status"] == "CONDITIONAL"
    assert "คำนวณเมื่อ trigger" not in str(trade)
    assert "4,397.00" in trade["entry"]
    assert "4,247.00" in trade["entry"]
