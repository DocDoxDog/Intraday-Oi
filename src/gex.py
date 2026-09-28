"""GC/Gold options GEX calculation from QuikStrike strike rows.

Dealer-convention GEX:
    call_gex = +gamma * call_OI * contract_multiplier * F^2 * 0.01
    put_gex  = -gamma * put_OI  * contract_multiplier * F^2 * 0.01

This is dollar gamma exposure for a 1% move in the underlying futures.
It is a positioning convention, not a claim about actual dealer inventory.
"""
from __future__ import annotations

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
                # Linear interpolation in cumulative GEX.
                return ps + (strike - ps) * (-pv) / (value - pv)
        previous = (strike, value)
    return None


def calculate_gex(rows: list[dict], future_price: float | None, multiplier: float = GC_CONTRACT_MULTIPLIER) -> dict:
    """Return per-strike GEX plus aggregate walls/flip.

    Requires QuikStrike's gamma, oiCall and oiPut. Missing/zero gamma rows
    are retained but contribute zero. No synthetic Greeks are generated.
    """
    F = _num(future_price)
    if F is None or F <= 0:
        return {"status": "unavailable", "reason": "future_price_missing", "rows": []}

    out = []
    for raw in rows:
        strike = _num(raw.get("strike"))
        gamma = _num(raw.get("gamma"))
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
    gamma_flip = _crossing_level(out, "cumulative_gex")

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
        "gamma_flip": gamma_flip,
        "positive_gamma": net > 0,
        "rows": out,
    }


def enrich_raw_series(raw_series: dict, future_price: float | None) -> dict:
    result = calculate_gex(raw_series.get("strike_rows") or [], future_price)
    raw_series["gex"] = result
    if result.get("status") == "ok":
        for row in raw_series.get("strike_rows") or []:
            strike = row.get("strike")
            match = next((g for g in result["rows"] if g["strike"] == strike), None)
            if match:
                row.update({
                    "call_gex": match["call_gex"],
                    "put_gex": match["put_gex"],
                    "net_gex": match["net_gex"],
                    "cumulative_gex": match["cumulative_gex"],
                })
    return raw_series
