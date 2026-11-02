"""Deterministic quantitative analytics layer.

Financial-engineering metrics are computed from observed market data only.
This module is descriptive: it does not create a directional alpha score.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import erf, log, sqrt
from typing import Any


def _n(v: Any) -> float | None:
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ratio(a: Any, b: Any) -> float | None:
    x, y = _n(a), _n(b)
    if x is None or y is None or y == 0:
        return None
    return x / y


def _return(now: Any, old: Any) -> float | None:
    a, b = _n(now), _n(old)
    if a is None or b is None or b == 0:
        return None
    return a / b - 1.0


def _iv_slope(term: list[dict[str, Any]]) -> float | None:
    rows = [(_n(x.get("dte")), _n(x.get("iv"))) for x in term if isinstance(x, dict)]
    rows = [(d, iv) for d, iv in rows if d is not None and iv is not None and d >= 0]
    if len(rows) < 2:
        return None
    rows.sort()
    d1, v1 = rows[0]
    d2, v2 = rows[-1]
    if d2 == d1:
        return None
    return (v2 - v1) / (d2 - d1)


# ---------------------------------------------------------------------------
# OHLC realized volatility and options-implied horizon risk (descriptive only)
# ---------------------------------------------------------------------------
TRADING_HOURS_PER_DAY = 23.0
TRADING_DAYS_PER_YEAR = 252.0
_BARS_PER_DAY = {"m1": 1380, "m5": 276, "m15": 92, "h1": 23}
_BAR_MINUTES = {"m1": 1, "m5": 5, "m15": 15, "h1": 60}


def horizon_sigma(price: float | None, iv_pct: float | None, hours: float) -> float | None:
    """One-sigma price distance in points over the requested trading hours."""
    p, iv = _n(price), _n(iv_pct)
    if p is None or iv is None or p <= 0 or iv < 0 or hours < 0:
        return None
    return p * (iv / 100.0) * sqrt(hours / (TRADING_HOURS_PER_DAY * TRADING_DAYS_PER_YEAR))


def stop_touch_probability(distance: float | None, sigma: float | None) -> float | None:
    """Driftless reflection-principle barrier-touch estimate; not a win probability."""
    d, sg = _n(distance), _n(sigma)
    if d is None or sg is None or sg <= 0 or d < 0:
        return None
    probability = 2.0 * (1.0 - 0.5 * (1.0 + erf((d / sg) / sqrt(2.0))))
    return min(1.0, max(0.0, probability))


def _interp(points: list[tuple[float, float]], x: float) -> float | None:
    points = sorted(points)
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


def atm_iv(
    rows: list[dict[str, Any]] | None,
    forward: Any,
    max_gap_pct: float = 0.02,
) -> float | None:
    """Interpolate per-strike IV at futures forward; never substitute a distant wing."""
    fwd = _n(forward)
    if fwd is None or fwd <= 0:
        return None
    points = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        strike, iv = _n(row.get("strike")), _n(row.get("vol"))
        if strike is not None and iv is not None and iv > 0:
            points.append((strike, iv))
    if len(points) < 2:
        return None
    interpolated = _interp(points, fwd)
    if interpolated is not None:
        return interpolated
    nearest = min(points, key=lambda point: abs(point[0] - fwd))
    return nearest[1] if abs(nearest[0] - fwd) / fwd <= max_gap_pct else None


def skew_25d(rows: list[dict[str, Any]] | None) -> float | None:
    """25-delta put IV minus 25-delta call IV, in vol points."""
    calls, puts = [], []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        iv = _n(row.get("vol"))
        call_delta, put_delta = _n(row.get("callDelta")), _n(row.get("putDelta"))
        if iv is None or iv <= 0:
            continue
        if call_delta is not None:
            calls.append((abs(call_delta), iv))
        if put_delta is not None:
            puts.append((abs(put_delta), iv))
    if len(calls) < 2 or len(puts) < 2:
        return None
    call_scale = 100.0 if max(delta for delta, _ in calls) > 1.5 else 1.0
    put_scale = 100.0 if max(delta for delta, _ in puts) > 1.5 else 1.0
    call_25 = _interp([(delta / call_scale, iv) for delta, iv in calls], 0.25)
    put_25 = _interp([(delta / put_scale, iv) for delta, iv in puts], 0.25)
    return put_25 - call_25 if call_25 is not None and put_25 is not None else None


def _parse_bar_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def realized_vol_from_bars(
    bars: list[dict[str, Any]] | None,
    tf: str = "m5",
    lookback_bars: int | None = None,
    min_bars: int = 30,
) -> dict[str, Any]:
    """Annualized close-to-close and Parkinson RV; long maintenance gaps are excluded."""
    timeframe = str(tf).lower()
    per_day, minutes = _BARS_PER_DAY.get(timeframe), _BAR_MINUTES.get(timeframe)
    if per_day is None or minutes is None:
        return {"status": "UNKNOWN", "reason": "unsupported_timeframe", "tf": timeframe}
    clean = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        high, low, close = _n(bar.get("high")), _n(bar.get("low")), _n(bar.get("close"))
        timestamp = _parse_bar_time(bar.get("datetime") or bar.get("bar_time"))
        if high is None or low is None or close is None or timestamp is None:
            continue
        if high < low or low <= 0 or close <= 0:
            continue
        clean.append((timestamp, high, low, close))
    clean.sort(key=lambda item: item[0])
    lookback = lookback_bars or per_day
    clean = clean[-(lookback + 1):]
    if len(clean) < min_bars:
        return {"status": "UNKNOWN", "reason": "insufficient_bars", "tf": timeframe, "bars": len(clean)}

    returns, parkinson_terms = [], []
    max_gap_seconds = minutes * 60 * 3
    for (time0, _high0, _low0, close0), (time1, high1, low1, close1) in zip(clean, clean[1:]):
        parkinson_terms.append(log(high1 / low1) ** 2)
        if (time1 - time0).total_seconds() <= max_gap_seconds:
            returns.append(log(close1 / close0))
    if len(returns) < min_bars - 1:
        return {"status": "UNKNOWN", "reason": "insufficient_contiguous_returns", "tf": timeframe, "bars": len(clean)}

    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    annualizer = sqrt(per_day * TRADING_DAYS_PER_YEAR)
    close_to_close = sqrt(max(variance, 0.0)) * annualizer * 100.0
    parkinson = sqrt(
        sum(parkinson_terms) / (4.0 * log(2.0) * len(parkinson_terms))
    ) * annualizer * 100.0
    return {
        "status": "OK",
        "tf": timeframe,
        "bars": len(clean),
        "contiguous_returns": len(returns),
        "close_to_close_pct": close_to_close,
        "parkinson_pct": parkinson,
        "method": "ohlc_realized_vol_gap_filtered_trading_time",
    }



def _row_field(row: dict[str, Any], *aliases: str) -> float | None:
    normalized = {"".join(ch for ch in str(k).lower() if ch.isalnum()): v for k, v in row.items()}
    for alias in aliases:
        value = _n(normalized.get("".join(ch for ch in alias.lower() if ch.isalnum())))
        if value is not None:
            return value
    return None


def _options_surface(rows: list[dict[str, Any]], underlying: float | None) -> dict[str, Any]:
    """Derive max-pain, moneyness, ATM and IV-surface evidence from observed strikes."""
    if not rows or underlying is None:
        return {"status": "UNKNOWN", "reason": "missing_strike_rows_or_underlying"}
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        strike = _n(row.get("strike"))
        if strike is None:
            continue
        clean.append({
            "strike": strike,
            "call_oi": _n(row.get("oiCall")) or 0.0,
            "put_oi": _n(row.get("oiPut")) or 0.0,
            "iv": _n(row.get("vol")),
            "call_iv": _row_field(row, "callIV", "callImpliedVol", "callVol"),
            "put_iv": _row_field(row, "putIV", "putImpliedVol", "putVol"),
            "distance": abs(strike - underlying),
        })
    if not clean:
        return {"status": "UNKNOWN", "reason": "no_valid_strikes"}
    clean.sort(key=lambda x: x["strike"])
    atm = min(clean, key=lambda x: x["distance"])

    totals = {"call": {"ITM": 0.0, "ATM": 0.0, "OTM": 0.0},
              "put": {"ITM": 0.0, "ATM": 0.0, "OTM": 0.0}}
    for x in clean:
        if x["strike"] == atm["strike"]:
            cb = pb = "ATM"
        else:
            cb = "ITM" if x["strike"] < underlying else "OTM"
            pb = "ITM" if x["strike"] > underlying else "OTM"
        totals["call"][cb] += x["call_oi"]
        totals["put"][pb] += x["put_oi"]

    pain = []
    for settle in (x["strike"] for x in clean):
        payout = sum(
            x["call_oi"] * max(settle - x["strike"], 0.0)
            + x["put_oi"] * max(x["strike"] - settle, 0.0)
            for x in clean
        )
        pain.append((payout, abs(settle - underlying), settle))
    pain.sort(key=lambda x: (x[0], x[1]))
    max_pain = pain[0][2] if pain else None

    wing = [x for x in clean if x["distance"] > 0]
    max_dist = max((x["distance"] for x in wing), default=0.0)
    threshold = max_dist * 0.35
    call_iv = [x["call_iv"] for x in wing if x["strike"] > underlying and x["distance"] >= threshold and x["call_iv"] is not None]
    put_iv = [x["put_iv"] for x in wing if x["strike"] < underlying and x["distance"] >= threshold and x["put_iv"] is not None]
    if call_iv and put_iv:
        c, p = sum(call_iv) / len(call_iv), sum(put_iv) / len(put_iv)
        skew = {
            "status": "AVAILABLE",
            "method": "OTM_WING_IV_AVERAGE",
            "call_otm_iv": round(c, 5),
            "put_otm_iv": round(p, 5),
            "risk_reversal_put_minus_call": round(p - c, 5),
        }
    else:
        curve = [(x["strike"], x["iv"]) for x in clean if x["iv"] is not None]
        slope = None
        if len(curve) >= 3 and curve[-1][0] != curve[0][0]:
            slope = (curve[-1][1] - curve[0][1]) / (curve[-1][0] - curve[0][0])
        skew = {
            "status": "CURVE_ONLY" if slope is not None else "UNKNOWN",
            "method": "SINGLE_IV_STRIKE_CURVE",
            "strike_iv_slope": round(slope, 8) if slope is not None else None,
            "limitation": "No separate call/put IV was exposed by source rows.",
        }

    return {
        "status": "AVAILABLE",
        "underlying": underlying,
        "atm": {
            "strike": atm["strike"], "distance": atm["distance"],
            "iv": atm["iv"], "call_oi": atm["call_oi"], "put_oi": atm["put_oi"],
        },
        "moneyness_oi": totals,
        "max_pain": {
            "strike": max_pain,
            "distance": max_pain - underlying if max_pain is not None else None,
            "distance_pct": (max_pain / underlying - 1.0) if max_pain is not None and underlying else None,
            "method": "OI_WEIGHTED_EXPIRY_PAYOUT_MINIMIZATION",
        },
        "iv_skew": skew,
        "source_strikes": len(clean),
    }


def enrich_quant_metrics(parsed: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach a deterministic quant_metrics evidence block to market_state."""
    history = history or {}
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    flow = state.get("flow") or {}
    gamma = state.get("gamma") or {}
    vol = state.get("volatility") or {}

    futures = _n(parsed.get("future_price"))
    cfd = _n(parsed.get("cfd_price"))
    basis = _n(parsed.get("basis_diff"))
    oi_total = _n(flow.get("oi_total"))
    put_oi = _n(flow.get("oi_put"))
    call_oi = _n(flow.get("oi_call"))
    put_chg = _n(flow.get("oi_change_put"))
    call_chg = _n(flow.get("oi_change_call"))
    gex = _n(gamma.get("net_gex"))
    strike_rows = raw.get("strike_rows") or []
    atm_from_state = _n(vol.get("atm_iv"))
    atm_from_rows = atm_iv(strike_rows, futures)
    iv = atm_from_state if atm_from_state is not None else atm_from_rows
    iv_source = (
        "market_state_atm_iv" if atm_from_state is not None
        else "atm_interpolated_at_forward" if atm_from_rows is not None
        else "state_or_parsed_mean"
    )
    if iv is None:
        # The parser field is a chain mean, not an ATM observation.
        iv = _n(vol.get("iv"))
    if iv is None:
        iv = _n(parsed.get("vol", parsed.get("iv")))
    skew25 = _n(vol.get("skew_25d"))
    if skew25 is None:
        skew25 = skew_25d(strike_rows)
    dte = _n(parsed.get("dte"))

    hour = history.get("hour_ago") or {}
    two = history.get("two_hours_ago") or {}
    today = history.get("today") or {}
    yesterday = history.get("yesterday") or {}

    hour_price = _n(hour.get("future_price"))
    two_price = _n(two.get("future_price"))
    today_open = _n(today.get("future_price_open"))
    yesterday_close = _n(yesterday.get("future_price_last"))

    returns = {
        "1h": _return(futures, hour_price),
        "2h": _return(futures, two_price),
        "session": _return(futures, today_open),
        "vs_yesterday_close": _return(futures, yesterday_close),
    }

    basis_pct_cfd = _ratio(basis, cfd)
    basis_abs_pct = abs(basis_pct_cfd) if basis_pct_cfd is not None else None

    call_put_ratio = _ratio(call_oi, put_oi)
    oi_imbalance = (
        _ratio(call_oi - put_oi, call_oi + put_oi)
        if call_oi is not None and put_oi is not None and call_oi + put_oi != 0
        else None
    )

    activity_total = (
        abs(put_chg) + abs(call_chg)
        if put_chg is not None and call_chg is not None
        else None
    )
    activity_share_call = (
        _ratio(abs(call_chg), activity_total)
        if call_chg is not None and activity_total is not None
        else None
    )
    activity_share_put = (
        _ratio(abs(put_chg), activity_total)
        if put_chg is not None and activity_total is not None
        else None
    )

    gex_per_oi = _ratio(gex, oi_total)

    call_wall = _n(gamma.get("call_wall"))
    put_wall = _n(gamma.get("put_wall"))
    distance_call = _return(cfd, call_wall)
    distance_put = _return(cfd, put_wall)

    term = vol.get("iv_term_structure") or []
    skew = _n(vol.get("skew"))
    term_slope = _iv_slope(term)
    options_surface = _options_surface(strike_rows, futures)

    technical = parsed.get("technical_context") or {}
    ohlcv = technical.get("ohlcv") or {}
    def _bars_for(*names):
        wanted = {str(name).lower() for name in names}
        for key, value in ohlcv.items():
            if str(key).lower() in wanted and isinstance(value, list):
                return value
        return None
    realized_vol = {
        "m5": realized_vol_from_bars(_bars_for("m5", "5m", "5min"), "m5"),
        "m15": realized_vol_from_bars(_bars_for("m15", "15m", "15min"), "m15"),
        "h1": realized_vol_from_bars(_bars_for("h1", "1h", "60m"), "h1"),
    }
    rv_m5 = realized_vol.get("m5") or {}
    rv_value = _n(rv_m5.get("close_to_close_pct")) if rv_m5.get("status") == "OK" else None
    horizon_moves = {
        "1h": horizon_sigma(futures, iv, 1.0),
        "4h": horizon_sigma(futures, iv, 4.0),
        "1d": horizon_sigma(futures, iv, TRADING_HOURS_PER_DAY),
    }

    # Options-implied expected move from ATM IV and time-to-expiry.
    # This is a magnitude/range estimate, not a directional forecast.
    expected_range = None
    if futures is not None and iv is not None and dte is not None and futures > 0 and iv >= 0 and dte >= 0:
        one_sigma = futures * (iv / 100.0) * sqrt(dte / 365.0)
        expected_range = {
            "one_sigma": one_sigma,
            "two_sigma": one_sigma * 2.0,
            "one_sigma_low": futures - one_sigma,
            "one_sigma_high": futures + one_sigma,
            "two_sigma_low": futures - 2.0 * one_sigma,
            "two_sigma_high": futures + 2.0 * one_sigma,
            "method": "ATM_IV_BLACK76_MAGNITUDE_APPROX",
            "direction": "UNKNOWN",
        }

    observed_returns = [x for x in returns.values() if x is not None]
    realized_vol_proxy = None
    if len(observed_returns) >= 2:
        mean_r = sum(observed_returns) / len(observed_returns)
        var = sum((r - mean_r) ** 2 for r in observed_returns) / (len(observed_returns) - 1)
        realized_vol_proxy = sqrt(max(var, 0.0))

    flags: list[str] = []
    if basis_abs_pct is not None and basis_abs_pct >= 0.0025:
        flags.append("CROSS_INSTRUMENT_DISLOCATION")
    if dte is not None and dte <= 1:
        flags.append("NEAR_EXPIRY")
    if gex is not None and gex < 0:
        flags.append("NEGATIVE_GAMMA_CONTEXT")
    elif gex is not None and gex > 0:
        flags.append("POSITIVE_GAMMA_CONTEXT")
    if iv is not None and iv >= 25:
        flags.append("ELEVATED_IV")
    if term_slope is not None and term_slope < 0:
        flags.append("INVERTED_IV_TERM_STRUCTURE")
    if oi_imbalance is not None and abs(oi_imbalance) >= 0.25:
        flags.append("OI_IMBALANCE")

    metrics = {
        "returns": returns,
        "basis": {
            "absolute": basis,
            "pct_of_cfd": basis_pct_cfd,
            "abs_pct_of_cfd": basis_abs_pct,
        },
        "open_interest": {
            "call_put_ratio": call_put_ratio,
            "imbalance": oi_imbalance,
            "activity_total": activity_total,
            "activity_share_call": activity_share_call,
            "activity_share_put": activity_share_put,
        },
        "gamma": {
            "net_gex": gex,
            "gex_per_total_oi": gex_per_oi,
            "distance_to_call_wall_return": distance_call,
            "distance_to_put_wall_return": distance_put,
            "interpretation": (
                "POSITIVE_GAMMA_CONTEXT" if gex is not None and gex > 0
                else "NEGATIVE_GAMMA_CONTEXT" if gex is not None and gex < 0
                else "UNKNOWN"
            ),
        },
        "volatility": {
            "implied_vol": iv,
            "implied_vol_source": iv_source,
            "atm_iv": iv,
            "skew_25d_put_minus_call": skew25,
            "expected_range": expected_range,
            "realized_vol_proxy": realized_vol_proxy,
            "realized_vol": realized_vol,
            "iv_minus_realized_m5_close_to_close": iv - rv_value if iv is not None and rv_value is not None else None,
            "iv_minus_realized_proxy": iv - realized_vol_proxy if iv is not None and realized_vol_proxy is not None else None,
            "horizon_sigma_points": horizon_moves,
            "iv_term_slope_per_dte": term_slope,
            "atm_skew": skew,
            "options_surface": options_surface,
        },
        "options_surface": options_surface,
        "expiry": {"dte": dte},
        "risk_flags": flags,
        "method": "deterministic-financial-math-v1",
        "limitations": [
            "Sparse snapshot returns are a proxy, not a full realized-volatility estimator.",
            "GEX is exposure context; it does not reveal dealer inventory or hedge direction.",
            "OI changes identify activity, not aggressor side.",
        ],
    }
    state["quant_metrics"] = metrics
    raw["market_state"] = state
    return parsed
