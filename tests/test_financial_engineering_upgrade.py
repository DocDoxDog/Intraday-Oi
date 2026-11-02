from datetime import datetime, timedelta, timezone

from src.gex import calculate_gex, gamma_profile
from src.quant_metrics import atm_iv, horizon_sigma, realized_vol_from_bars, skew_25d
from src.risk_engine import evaluate_setup_risk, stop_noise_assessment


def _gamma_rows(forward=4050.0):
    rows = []
    for strike in range(3800, 4400, 10):
        rows.append({
            "strike": float(strike),
            "vol": 20.0 + abs(strike - forward) / forward * 35.0,
            "oiCall": 2000 if strike >= 4200 else 100,
            "oiPut": 2000 if strike <= 3900 else 100,
        })
    return rows


def test_spot_grid_gamma_profile_exposes_assumptions_not_dealer_facts():
    profile = gamma_profile(_gamma_rows(), 4050.0, 7.0, span=0.08)
    assert profile["status"] == "ok"
    assert set(profile["scenarios"]) == {
        "equity_convention",
        "dealer_short_calls",
        "dealer_short_both",
    }
    assert profile["sign_consensus"] is False
    assert "assumed" in profile["limitation"].lower() or "assumption" in profile["limitation"].lower()
    result = calculate_gex(_gamma_rows(), 4050.0, 7.0)
    assert result["gamma_profile"]["status"] == "ok"
    assert result["gamma_flip_method"] == "spot_grid"


def test_spot_grid_gamma_profile_fails_closed_without_iv_or_dte():
    assert gamma_profile(
        [{"strike": 4050, "oiCall": 10, "oiPut": 10}],
        4050,
        7,
    )["status"] == "unavailable"
    assert gamma_profile(_gamma_rows(), 4050, None)["status"] == "unavailable"


def test_atm_iv_and_25d_skew_use_observed_strike_fields():
    rows = []
    for i, strike in enumerate(range(3800, 4301, 50)):
        call_delta = 0.95 - i * 0.09
        rows.append({
            "strike": strike,
            "vol": 22.0 - i * 0.25,
            "callDelta": call_delta,
            "putDelta": -(1.0 - call_delta),
        })
    assert abs(atm_iv(rows, 4050.0) - 19.5) < 1e-9
    assert skew_25d(rows) is not None
    assert atm_iv([{"strike": 4000, "vol": 20}], 4000) is None


def test_realized_vol_uses_ohlc_and_returns_unknown_for_sparse_data():
    base = datetime(2026, 10, 27, tzinfo=timezone.utc)
    bars, price = [], 4000.0
    for index in range(100):
        next_price = price + (1.0 if index % 2 == 0 else -0.8)
        bars.append({
            "datetime": (base + timedelta(minutes=5 * index)).isoformat(),
            "open": price,
            "high": max(price, next_price) + 0.2,
            "low": min(price, next_price) - 0.2,
            "close": next_price,
        })
        price = next_price
    rv = realized_vol_from_bars(bars, "m5")
    assert rv["status"] == "OK"
    assert rv["close_to_close_pct"] > 0
    assert rv["parkinson_pct"] > 0
    assert realized_vol_from_bars(bars[:10], "m5")["status"] == "UNKNOWN"


def test_horizon_sigma_and_stop_noise_are_advisory_only():
    sigma = horizon_sigma(4000.0, 20.0, 1.0)
    assert sigma is not None and sigma > 0
    result = evaluate_setup_risk(
        "LONG",
        4000.0,
        3995.0,
        [4010.0, 4020.0],
        iv_pct=20.0,
        ref_price=4000.0,
    )
    assert result["status"] == "PASS"
    assert "STOP_INSIDE_1H_NOISE" in result["warnings"]
    assert 0.0 < result["recommended_risk_scale"] < 1.0
    unknown = stop_noise_assessment(5.0, None, 4000.0)
    assert unknown["status"] == "UNKNOWN"
    assert unknown["recommended_risk_scale"] is None
