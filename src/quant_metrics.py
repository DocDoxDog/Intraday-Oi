"""Deterministic quantitative analytics layer.

Financial-engineering metrics are computed from observed market data only.
This module is descriptive: it does not create a directional alpha score.
"""
from __future__ import annotations

from math import sqrt
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
    iv = _n(vol.get("iv"))
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
    activity_share_call = _ratio(abs(call_chg), activity_total)
    activity_share_put = _ratio(abs(put_chg), activity_total)

    gex_per_oi = _ratio(gex, oi_total)

    call_wall = _n(gamma.get("call_wall"))
    put_wall = _n(gamma.get("put_wall"))
    distance_call = _return(cfd, call_wall)
    distance_put = _return(cfd, put_wall)

    term = vol.get("iv_term_structure") or []
    skew = _n(vol.get("skew"))
    term_slope = _iv_slope(term)

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
            "realized_vol_proxy": realized_vol_proxy,
            "iv_minus_realized_proxy": iv - realized_vol_proxy if iv is not None and realized_vol_proxy is not None else None,
            "iv_term_slope_per_dte": term_slope,
            "atm_skew": skew,
        },
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
