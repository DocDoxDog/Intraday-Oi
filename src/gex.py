"""GC/Gold options GEX calculation.

Research-grade calculation layer:
- keeps the existing default convention for compatibility;
- makes the sign convention explicit and versioned;
- distinguishes observed/derived gamma from assumed dealer sign;
- never labels signed OI-GEX as observed dealer inventory.
"""
from __future__ import annotations

import math
from typing import Any

GC_CONTRACT_MULTIPLIER = 100.0
GEX_CALCULATION_VERSION = "gex-v2"


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _crossing_level(rows, key):
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
                return (
                    strike
                    if value == previous_value
                    else previous_strike
                    + (strike - previous_strike) * (-previous_value) / (value - previous_value)
                )
        prev = (strike, value)
    return None


def black76_gamma(F, strike, iv_percent, dte_days, risk_free_rate=0.0):
    if F <= 0 or strike <= 0 or iv_percent is None or dte_days <= 0:
        return None
    sigma = iv_percent / 100.0
    T = dte_days / 365.0
    if sigma <= 0:
        return None
    d1 = (
        math.log(F / strike) + 0.5 * sigma * sigma * T
    ) / (sigma * math.sqrt(T))
    discount = math.exp(-float(risk_free_rate) * T)
    return discount * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (
        F * sigma * math.sqrt(T)
    )


def _sign(option_type: str, convention: str) -> int:
    option_type = str(option_type).upper()
    if convention in {"CALL_PLUS_PUT_MINUS", "DEALER_SHORT_PUBLIC"}:
        return 1 if option_type == "CALL" else -1
    if convention == "CALL_MINUS_PUT_PLUS":
        return -1 if option_type == "CALL" else 1
    if convention == "GROSS_ABS":
        return 1
    raise ValueError(f"unsupported_gex_sign_convention:{convention}")


def calculate_gex(
    rows,
    future_price,
    dte_days=None,
    multiplier=GC_CONTRACT_MULTIPLIER,
    convention="DEALER_SHORT_PUBLIC",
    risk_free_rate=0.0,
):
    F = _num(future_price)
    if F is None or F <= 0:
        return {"status": "unavailable", "reason": "future_price_missing", "rows": []}

    if convention == "GROSS_ABS":
        public_sign_assumption = "none; gross absolute gamma"
    elif convention == "DEALER_SHORT_PUBLIC":
        public_sign_assumption = "calls_positive_puts_negative"
    else:
        public_sign_assumption = convention.lower()

    out = []
    for raw in rows:
        strike = _num(raw.get("strike"))
        gamma = _num(raw.get("gamma"))
        source = "quikstrike" if gamma is not None else "missing"

        if gamma is None and strike is not None:
            iv = _num(raw.get("vol"))
            dte = _num(dte_days)
            if iv is not None and dte is not None:
                gamma = black76_gamma(F, strike, iv, dte, risk_free_rate)
                source = "black76_from_iv"

        if strike is None or gamma is None:
            continue

        call_oi = _num(raw.get("oiCall")) or 0.0
        put_oi = _num(raw.get("oiPut")) or 0.0
        scale = multiplier * (F ** 2) * 0.01

        call_gex = gamma * call_oi * scale * _sign("CALL", convention)
        put_gex = gamma * put_oi * scale * _sign("PUT", convention)

        x = dict(raw)
        x.update(
            {
                "call_gex": call_gex,
                "put_gex": put_gex,
                "net_gex": call_gex + put_gex,
                "gamma": gamma,
                "gex_multiplier": multiplier,
                "gamma_source": source,
                "gex_sign_convention": convention,
                "gex_calculation_version": GEX_CALCULATION_VERSION,
            }
        )
        out.append(x)

    out.sort(key=lambda r: r["strike"])
    cumulative = 0.0
    for row in out:
        cumulative += row["net_gex"]
        row["cumulative_gex"] = cumulative

    net = sum(row["net_gex"] for row in out)
    return {
        "status": "ok" if out else "unavailable",
        "underlying": "GC",
        "future_price": F,
        "contract_multiplier": multiplier,
        "gex_unit": "USD per 1% underlying move",
        "convention": convention,
        "public_sign_assumption": public_sign_assumption,
        "dealer_position_observed": False,
        "net_gex": net,
        "call_gex_total": sum(row["call_gex"] for row in out),
        "put_gex_total": sum(row["put_gex"] for row in out),
        "call_wall": max(out, key=lambda r: r["call_gex"])["strike"] if out else None,
        "put_wall": min(out, key=lambda r: r["put_gex"])["strike"] if out else None,
        "max_abs_gex_strike": max(out, key=lambda r: abs(r["net_gex"]))["strike"] if out else None,
        "gamma_flip": _crossing_level(out, "cumulative_gex"),
        "positive_gamma": net > 0 if convention != "GROSS_ABS" else None,
        "source_gamma_count": sum(r["gamma_source"] == "quikstrike" for r in out),
        "derived_gamma_count": sum(r["gamma_source"] == "black76_from_iv" for r in out),
        "calculation_version": GEX_CALCULATION_VERSION,
        "rows": out,
    }


def enrich_raw_series(raw_series, future_price):
    result = calculate_gex(
        raw_series.get("strike_rows") or [],
        future_price,
        raw_series.get("dte"),
    )
    raw_series["gex"] = result
    if result.get("status") == "ok":
        by = {r["strike"]: r for r in result["rows"]}
        for row in raw_series.get("strike_rows") or []:
            match = by.get(row.get("strike"))
            if match:
                row.update(
                    {
                        key: match[key]
                        for key in (
                            "call_gex",
                            "put_gex",
                            "net_gex",
                            "cumulative_gex",
                            "gamma_source",
                            "gex_sign_convention",
                            "gex_calculation_version",
                        )
                    }
                )
    return raw_series
