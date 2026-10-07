"""GC/Gold options GEX calculation from source OI/IV rows.

Missing OI is UNKNOWN, never silently converted to zero.
"""
from __future__ import annotations

import math
from typing import Any

GC_CONTRACT_MULTIPLIER = 100.0\nGEX_MODEL = "dealer_short_all"\nGEX_MODEL_VERSION = "canonical-gex-v2"


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
            "gamma_source": source,\n            "gex_model": GEX_MODEL,\n            "gex_model_version": GEX_MODEL_VERSION,
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

    return {
        "status": "ok" if out else "unavailable",
        "underlying": "GC",
        "future_price": F,
        "contract_multiplier": multiplier,
        "gex_unit": "USD per 1% underlying move",
        "convention": "dealer_call_positive_put_negative",\n        "model": GEX_MODEL,\n        "model_version": GEX_MODEL_VERSION,
        "net_gex": net,
        "call_gex_total": call_total,
        "put_gex_total": put_total,
        "call_wall": max(call_rows, key=lambda row: row["call_gex"])["strike"] if call_rows else None,
        "put_wall": min(put_rows, key=lambda row: row["put_gex"])["strike"] if put_rows else None,
        "max_abs_gex_strike": max(net_rows, key=lambda row: abs(row["net_gex"]))["strike"] if net_rows else None,
        "gamma_flip": _crossing_level(net_rows, "cumulative_gex"),
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
