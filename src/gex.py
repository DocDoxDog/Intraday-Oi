"""GC/Gold options GEX calculation from source OI/IV rows.

Missing OI is UNKNOWN, never silently converted to zero.
"""
from __future__ import annotations

import math
from typing import Any

GC_CONTRACT_MULTIPLIER = 100.0


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _crossing_level(rows: list[dict[str, Any]], key: str) -> float | None:
    prev = None
    for row in rows:
        value = _num(row.get(key))
        strike = _num(row.get("strike"))
        if value is None or strike is None:
            continue
        if prev is not None:
            previous_strike, previous_value = prev
            if previous_value == 0:
                return previous_strike
            if (previous_value < 0 <= value) or (previous_value > 0 >= value):
                if value == previous_value:
                    return strike
                return previous_strike + (strike - previous_strike) * (-previous_value) / (value - previous_value)
        prev = (strike, value)
    return None


def black76_gamma(F: float, strike: float, iv_percent: float | None, dte_days: float) -> float | None:
    if F <= 0 or strike <= 0 or iv_percent is None or dte_days <= 0:
        return None
    sigma = iv_percent / 100.0
    T = dte_days / 365.0
    if sigma <= 0:
        return None
    d1 = (math.log(F / strike) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    return math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (F * sigma * math.sqrt(T))


# ---------------------------------------------------------------------------
# Spot-grid gamma profile and dealer-sign scenarios.
# OI does not identify who is long or short; these are explicit assumptions.
# ---------------------------------------------------------------------------
SIGN_SCENARIOS: dict[str, tuple[float, float]] = {
    "equity_convention": (1.0, -1.0),
    "dealer_short_calls": (-1.0, 1.0),
    "dealer_short_both": (-1.0, -1.0),
}


def _row_iv(row: dict[str, Any]) -> float | None:
    iv = _num(row.get("vol"))
    return iv if iv is not None and iv > 0 else None


def _crossing_in_series(points: list[tuple[float, float]], anchor: float) -> float | None:
    """Return the zero crossing nearest the forward using linear interpolation."""
    best = None
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if y0 == 0:
            candidate = x0
        elif (y0 < 0 < y1) or (y0 > 0 > y1):
            candidate = x0 + (x1 - x0) * (-y0) / (y1 - y0)
        else:
            continue
        if best is None or abs(candidate - anchor) < abs(best - anchor):
            best = candidate
    return best


def gamma_profile(
    rows: list[dict[str, Any]],
    future_price: float,
    dte_days: float | None,
    *,
    multiplier: float = GC_CONTRACT_MULTIPLIER,
    span: float = 0.06,
    steps: int = 61,
) -> dict[str, Any]:
    """Reprice per-strike gamma across a hypothetical forward-price grid.

    A zero-gamma crossing is computed for each explicitly named dealer-sign
    convention. It is not presented as observed dealer inventory or intent.
    """
    forward, dte = _num(future_price), _num(dte_days)
    if forward is None or forward <= 0 or dte is None or dte <= 0:
        return {"status": "unavailable", "reason": "future_price_or_dte_missing", "scenarios": {}}
    usable = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        strike = _num(row.get("strike"))
        iv = _row_iv(row)
        call_oi, put_oi = _num(row.get("oiCall")), _num(row.get("oiPut"))
        if strike is not None and iv is not None and call_oi is not None and put_oi is not None:
            usable.append((strike, iv, call_oi, put_oi))
    if len(usable) < 3:
        return {"status": "unavailable", "reason": "insufficient_rows_with_iv_and_oi", "scenarios": {}}

    count = max(5, int(steps))
    grid = [forward * (1.0 - span + (2.0 * span) * i / (count - 1)) for i in range(count)]
    curves: dict[str, list[tuple[float, float]]] = {name: [] for name in SIGN_SCENARIOS}
    for spot in grid:
        scale = multiplier * spot * spot * 0.01
        call_gamma = put_gamma = 0.0
        for strike, iv, call_oi, put_oi in usable:
            gamma = black76_gamma(spot, strike, iv, dte)
            if gamma is None:
                continue
            call_gamma += gamma * call_oi * scale
            put_gamma += gamma * put_oi * scale
        for name, (call_sign, put_sign) in SIGN_SCENARIOS.items():
            curves[name].append((spot, call_sign * call_gamma + put_sign * put_gamma))

    scenarios: dict[str, Any] = {}
    for name, points in curves.items():
        at_forward = min(points, key=lambda point: abs(point[0] - forward))[1]
        scenarios[name] = {
            "net_gex_at_forward": at_forward,
            "zero_gamma_level": _crossing_in_series(points, forward),
            "sign_at_forward": "POSITIVE" if at_forward > 0 else "NEGATIVE" if at_forward < 0 else "ZERO",
        }
    signs = {item["sign_at_forward"] for item in scenarios.values()}
    return {
        "status": "ok",
        "method": "spot_grid_black76_per_strike_iv",
        "span_pct": span * 100.0,
        "rows_used": len(usable),
        "scenarios": scenarios,
        "sign_consensus": len(signs) == 1,
        "curve": [
            {"spot": round(spot, 2), "net_gex": round(value, 2)}
            for spot, value in curves["equity_convention"]
        ],
        "limitation": "Dealer sign is assumed; open interest does not identify the long/short holder.",
    }


def calculate_gex(
    rows: list[dict[str, Any]],
    future_price: float,
    dte_days: float | None = None,
    multiplier: float = GC_CONTRACT_MULTIPLIER,
) -> dict[str, Any]:
    F = _num(future_price)
    if F is None or F <= 0:
        return {"status": "unavailable", "reason": "future_price_missing", "rows": []}

    out = []
    for raw in rows:
        strike = _num(raw.get("strike"))
        gamma = _num(raw.get("gamma"))
        source = "quikstrike"
        if gamma is None and strike is not None:
            iv = _num(raw.get("vol"))
            dte = _num(dte_days)
            if iv is not None and dte is not None:
                gamma = black76_gamma(F, strike, iv, dte)
                source = "black76_from_iv"

        if strike is None or gamma is None:
            continue

        call_oi = _num(raw.get("oiCall"))
        put_oi = _num(raw.get("oiPut"))
        scale = multiplier * (F**2) * 0.01

        call_gex = gamma * call_oi * scale if call_oi is not None else None
        put_gex = -gamma * put_oi * scale if put_oi is not None else None
        net_gex = call_gex + put_gex if call_gex is not None and put_gex is not None else None

        item = dict(raw)
        item.update({
            "call_gex": call_gex,
            "put_gex": put_gex,
            "net_gex": net_gex,
            "gamma": gamma,
            "gex_multiplier": multiplier,
            "gamma_source": source,
        })
        out.append(item)

    out.sort(key=lambda r: r["strike"])
    cumulative = 0.0
    for row in out:
        net = _num(row.get("net_gex"))
        if net is None:
            row["cumulative_gex"] = None
        else:
            cumulative += net
            row["cumulative_gex"] = cumulative

    net_values = [_num(row.get("net_gex")) for row in out if _num(row.get("net_gex")) is not None]
    call_values = [_num(row.get("call_gex")) for row in out if _num(row.get("call_gex")) is not None]
    put_values = [_num(row.get("put_gex")) for row in out if _num(row.get("put_gex")) is not None]

    net = sum(net_values) if net_values else None
    call_total = sum(call_values) if call_values else None
    put_total = sum(put_values) if put_values else None

    call_rows = [row for row in out if _num(row.get("call_gex")) is not None]
    put_rows = [row for row in out if _num(row.get("put_gex")) is not None]
    net_rows = [row for row in out if _num(row.get("net_gex")) is not None]
    cumulative_flip = _crossing_level(net_rows, "cumulative_gex")
    profile = gamma_profile(rows, F, dte_days, multiplier=multiplier)
    grid_flip = (
        (profile.get("scenarios") or {}).get("equity_convention", {}).get("zero_gamma_level")
        if profile.get("status") == "ok" else None
    )

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
        "call_wall": max(call_rows, key=lambda row: row["call_gex"])["strike"] if call_rows else None,
        "put_wall": min(put_rows, key=lambda row: row["put_gex"])["strike"] if put_rows else None,
        "max_abs_gex_strike": max(net_rows, key=lambda row: abs(row["net_gex"]))["strike"] if net_rows else None,
        "gamma_flip": grid_flip if grid_flip is not None else cumulative_flip,
        "gamma_flip_method": "spot_grid" if grid_flip is not None else "cumulative_strike_crossing",
        "gamma_flip_cumulative": cumulative_flip,
        "gamma_profile": profile,
        "sign_consensus": profile.get("sign_consensus"),
        "positive_gamma": net > 0 if net is not None else None,
        "source_gamma_count": sum(row["gamma_source"] == "quikstrike" for row in out),
        "derived_gamma_count": sum(row["gamma_source"] == "black76_from_iv" for row in out),
        "rows": out,
    }


def enrich_raw_series(raw_series: dict[str, Any], future_price: float) -> dict[str, Any]:
    result = calculate_gex(
        raw_series.get("strike_rows") or [],
        future_price,
        raw_series.get("dte"),
    )
    raw_series["gex"] = result
    if result.get("status") == "ok":
        by = {row["strike"]: row for row in result["rows"]}
        for row in raw_series.get("strike_rows") or []:
            match = by.get(row.get("strike"))
            if match:
                row.update({
                    "call_gex": match["call_gex"],
                    "put_gex": match["put_gex"],
                    "net_gex": match["net_gex"],
                    "cumulative_gex": match["cumulative_gex"],
                    "gamma_source": match["gamma_source"],
                })
    return raw_series
