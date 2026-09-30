from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant.greeks.black76 import calculate_black76_greeks


GEX_CALCULATION_VERSION = "canonical-gex-v1"
GEX_SIGN_CONVENTIONS = (
    "DEALER_SHORT_PUBLIC",
    "CALL_MINUS_PUT_PLUS",
    "GROSS_ABS",
)


@dataclass(frozen=True)
class GEXConvention:
    name: str = "DEALER_SHORT_PUBLIC"

    @property
    def public_sign_assumption(self) -> str:
        if self.name == "DEALER_SHORT_PUBLIC":
            return "calls_positive_puts_negative_assumed_not_observed"
        if self.name == "CALL_MINUS_PUT_PLUS":
            return "calls_negative_puts_positive_assumed"
        if self.name == "GROSS_ABS":
            return "no_directional_sign_gross_absolute_gamma"
        raise ValueError(f"UNSUPPORTED_GEX_SIGN_CONVENTION:{self.name}")


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _sign(option_type: str, convention: str) -> int:
    side = option_type.upper()
    if convention == "DEALER_SHORT_PUBLIC":
        return 1 if side == "CALL" else -1
    if convention == "CALL_MINUS_PUT_PLUS":
        return -1 if side == "CALL" else 1
    if convention == "GROSS_ABS":
        return 1
    raise ValueError(f"UNSUPPORTED_GEX_SIGN_CONVENTION:{convention}")


def black76_gamma(
    futures_price: float,
    strike: float,
    iv_percent: float | None,
    dte_days: float,
    risk_free_rate: float = 0.0,
) -> float | None:
    if iv_percent is None or dte_days <= 0:
        return None
    try:
        return calculate_black76_greeks(
            futures_price,
            strike,
            iv_percent,
            dte_days / 365.0,
            "CALL",
            risk_free_rate=risk_free_rate,
            iv_unit="PERCENT",
            calculation_version="canonical-black76-greeks-v1",
        ).gamma
    except ValueError:
        return None


def _crossing_level(rows: list[dict], key: str) -> float | None:
    previous = None
    for row in rows:
        value = _num(row.get(key))
        strike = _num(row.get("strike"))
        if value is None or strike is None:
            continue
        if previous is not None:
            previous_strike, previous_value = previous
            if previous_value == 0:
                return previous_strike
            if (previous_value < 0 <= value) or (previous_value > 0 >= value):
                if value == previous_value:
                    return strike
                return previous_strike + (
                    (strike - previous_strike)
                    * (-previous_value)
                    / (value - previous_value)
                )
        previous = (strike, value)
    return None


def calculate_gex_result(
    rows,
    futures_price: float,
    *,
    dte_days: float | None = None,
    multiplier: float = 100.0,
    convention: str = "DEALER_SHORT_PUBLIC",
    risk_free_rate: float = 0.0,
    underlying: str = "GC",
    expiry_scope: str = "SELECTED_EXPIRY",
) -> dict:
    if convention not in GEX_SIGN_CONVENTIONS:
        raise ValueError(f"UNSUPPORTED_GEX_SIGN_CONVENTION:{convention}")

    F = _num(futures_price)
    if F is None or F <= 0:
        return {
            "status": "unavailable",
            "reason": "future_price_missing",
            "rows": [],
            "calculation_version": GEX_CALCULATION_VERSION,
        }

    result_rows = []
    scale = multiplier * (F ** 2) * 0.01

    for raw in rows:
        strike = _num(raw.get("strike"))
        if strike is None:
            continue

        gamma = _num(raw.get("gamma"))
        gamma_source = "quikstrike" if gamma is not None else "missing"
        if gamma is None and dte_days is not None:
            iv = _num(raw.get("vol"))
            if iv is not None:
                gamma = black76_gamma(
                    F,
                    strike,
                    iv,
                    dte_days,
                    risk_free_rate=risk_free_rate,
                )
                if gamma is not None:
                    gamma_source = "black76_from_iv"

        if gamma is None:
            continue

        call_oi = _num(raw.get("oiCall")) or 0.0
        put_oi = _num(raw.get("oiPut")) or 0.0
        call_gex = gamma * call_oi * scale * _sign("CALL", convention)
        put_gex = gamma * put_oi * scale * _sign("PUT", convention)

        row = dict(raw)
        row.update(
            {
                "gamma": gamma,
                "call_gex": call_gex,
                "put_gex": put_gex,
                "net_gex": call_gex + put_gex,
                "gex_multiplier": multiplier,
                "gamma_source": gamma_source,
                "gex_sign_convention": convention,
                "gex_calculation_version": GEX_CALCULATION_VERSION,
                "gex_unit": "USD per 1% underlying move",
                "expiry_scope": expiry_scope,
            }
        )
        result_rows.append(row)

    result_rows.sort(key=lambda row: row["strike"])
    cumulative = 0.0
    for row in result_rows:
        cumulative += row["net_gex"]
        row["cumulative_gex"] = cumulative

    net = sum(row["net_gex"] for row in result_rows)
    gross = sum(abs(row["call_gex"]) + abs(row["put_gex"]) for row in result_rows)
    call_rows = [row for row in result_rows if row["call_gex"] != 0]
    put_rows = [row for row in result_rows if row["put_gex"] != 0]

    return {
        "status": "ok" if result_rows else "unavailable",
        "underlying": underlying,
        "future_price": F,
        "contract_multiplier": multiplier,
        "gex_unit": "USD per 1% underlying move",
        "convention": convention,
        "gex_sign_convention": convention,
        "public_sign_assumption": GEXConvention(convention).public_sign_assumption,
        "dealer_position_observed": False,
        "expiry_scope": expiry_scope,
        "net_gex": net,
        "gross_gex": gross,
        "call_gex_total": sum(row["call_gex"] for row in result_rows),
        "put_gex_total": sum(row["put_gex"] for row in result_rows),
        "call_wall": (
            max(call_rows, key=lambda row: row["call_gex"])["strike"]
            if call_rows and convention != "GROSS_ABS"
            else None
        ),
        "put_wall": (
            min(put_rows, key=lambda row: row["put_gex"])["strike"]
            if put_rows and convention != "GROSS_ABS"
            else None
        ),
        "max_abs_gex_strike": (
            max(result_rows, key=lambda row: abs(row["net_gex"]))["strike"]
            if result_rows
            else None
        ),
        "gamma_flip": _crossing_level(result_rows, "cumulative_gex"),
        "positive_gamma": net > 0 if convention != "GROSS_ABS" else None,
        "source_gamma_count": sum(row["gamma_source"] == "quikstrike" for row in result_rows),
        "derived_gamma_count": sum(row["gamma_source"] == "black76_from_iv" for row in result_rows),
        "calculation_version": GEX_CALCULATION_VERSION,
        "rows": result_rows,
    }


def calculate_gex(*args, **kwargs) -> dict:
    return calculate_gex_result(*args, **kwargs)
