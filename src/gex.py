"""GC/Gold options GEX calculation from QuikStrike strike rows."""
from __future__ import annotations
import math
from typing import Any

GC_CONTRACT_MULTIPLIER = 100.0

def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def _crossing_level(rows: list[dict], key: str) -> float | None:
    previous = None
    for row in rows:
        value = _num(row.get(key))
        strike = _num(row.get("strike"))
        if value is None or strike is None:
            continue
        if previous is not None:
            ps, pv = previous
            if pv == 0:
                return ps
            if (pv < 0 <= value) or (pv > 0 >= value):
                if value == pv:
                    return strike
                return ps + (strike - ps) * (-pv) / (value - pv)
        previous = (strike, value)
    return None

def black76_gamma(futures_price: float, strike: float, iv_percent: float, dte_days: float) -> float | None:
    """Black-76 gamma per $1 move when QuikStrike does not expose gamma."""
    if futures_price <= 0 or strike <= 0 or iv_percent is None or dte_days <= 0:
        return None
    sigma = iv_percent / 100.0
    T = dte_days / 365.0
    if sigma <= 0 or T <= 0:
        return None
    d1 = (math.log(futures_price / strike) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    return pdf / (futures_price * sigma * math.sqrt(T))

def calculate_gex(
    rows: list[dict],
    future_price: float | None,
    dte_days: float | None = None,
    multiplier: float = GC_CONTRACT_MULTIPLIER,
) -> dict:
    """Return per-strike GEX plus aggregate walls/flip.

    If QuikStrike gamma is absent, Black-76 gamma is derived from IV + DTE.
    """
    F = _num(future_price)
    if F is None or F <= 0:
        return {"status": "unavailable", "reason": "future_price_missing", "rows": []}

    out = []
    for raw in rows:
        strike = _num(raw.get("strike"))
        gamma = _num(raw.get("gamma"))
        gamma_source = "quikstrike"
        if gamma is None:
            iv = _num(raw.get("vol"))
            dte = _num(dte_days)
            if iv is not None and dte is not None:
                gamma = black76_gamma(F, strike or 0, iv, dte)
                gamma_source = "black76_iv_fallback"
        call_oi = _num(raw.get("oiCall")) or 0.0
        put_oi = _num(raw.get("oiPut")) or 0.0
        if strike is None or gamma is None:
            continue
        scale = multiplier * (F ** 2) * 0.01
        call_gex = gamma * call_oi * scale
        put_gex = -gamma * put_oi * scale
        row = dict(raw)
        row.update({
            "call_gex": call_gex,
            "put_gex": put_gex,
            "net_gex": call_gex + put_gex,
            "gamma": gamma,
            "gex_multiplier": multiplier,
            "gamma_source": gamma_source,
        })
        out.append(row)

    out.sort(key=lambda r: r["strike"])
    cumulative = 0.0
    for row in out:
        cumulative += row["net_gex"]
        row["cumulative_gex"] = cumulative

    net = sum(r["net_gex"] for r in out)
    call_total = sum(r["call_gex"] for r in out)
    put_total = sum(r["put_gex"] for r in out)
    call_wall = max(out, key=lambda r: r["call_gex"])["strike"] if out else None
    put_wall = min(out, key=lambda r: r["put_gex"])["strike"] if out else None
    max_gamma = max(out, key=lambda r: abs(r["net_gex"]))["strike"] if out else None

    return {
        "status": "ok" if out else "unavailable",
        "underlying": "GC",
        "future_price": F,
        "contract_multiplier": multiplier,
        "gex_unit": "USD per 1% underlying move",
        "convention": "dealer_call_positive_put_negative",
        "net_gex": net,
        "call_gex_total": call_total,
        "put_gex_total": put_total,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "max_abs_gex_strike": max_gamma,
        "gamma_flip": _crossing_level(out, "cumulative_gex"),
        "positive_gamma": net > 0,
        "source_gamma_count": sum(r["gamma_source"] == "quikstrike" for r in out),
        "derived_gamma_count": sum(r["gamma_source"] == "black76_iv_fallback" for r in out),
        "rows": out,
    }

def enrich_raw_series(raw_series: dict, future_price: float | None) -> dict:
    result = calculate_gex(raw_series.get("strike_rows") or [], future_price, raw_series.get("dte"))
    raw_series["gex"] = result
    if result.get("status") == "ok":
        by_strike = {r["strike"]: r for r in result["rows"]}
        for row in raw_series.get("strike_rows") or []:
            match = by_strike.get(row.get("strike"))
            if match:
                row.update({
                    "call_gex": match["call_gex"],
                    "put_gex": match["put_gex"],
                    "net_gex": match["net_gex"],
                    "cumulative_gex": match["cumulative_gex"],
                    "gamma_source": match["gamma_source"],
                })
    return raw_series
