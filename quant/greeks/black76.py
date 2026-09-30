from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist


_N = NormalDist()


@dataclass(frozen=True)
class Black76Greeks:
    model: str
    calculation_version: str
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float
    iv_input_unit: str
    gamma_unit: str = "1 / futures-price"
    theta_unit: str = "currency per year"
    vega_unit: str = "currency per 1.0 volatility"


def normalize_iv(iv: float, unit: str = "PERCENT") -> float:
    value = float(iv)
    normalized = unit.upper()
    if normalized in {"PERCENT", "%"}:
        return value / 100.0
    if normalized in {"DECIMAL", "VOL"}:
        return value
    raise ValueError(f"UNSUPPORTED_IV_UNIT:{unit}")


def _d1_d2(F: float, K: float, sigma: float, T: float) -> tuple[float, float]:
    root_t = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * root_t)
    return d1, d1 - sigma * root_t


def black76_option_price(
    futures_price: float,
    strike: float,
    implied_volatility: float,
    expiry_years: float,
    option_type: str,
    risk_free_rate: float = 0.0,
    iv_unit: str = "DECIMAL",
) -> float:
    F = float(futures_price)
    K = float(strike)
    T = float(expiry_years)
    sigma = normalize_iv(implied_volatility, iv_unit)

    if F <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        raise ValueError("INVALID_BLACK76_INPUT")
    d1, d2 = _d1_d2(F, K, sigma, T)
    discount = math.exp(-risk_free_rate * T)
    t = option_type.upper()
    if t == "CALL":
        return discount * (F * _N.cdf(d1) - K * _N.cdf(d2))
    if t == "PUT":
        return discount * (K * _N.cdf(-d2) - F * _N.cdf(-d1))
    raise ValueError(f"UNKNOWN_OPTION_TYPE:{option_type}")


def calculate_black76_greeks(
    futures_price: float,
    strike: float,
    implied_volatility: float,
    expiry_years: float,
    option_type: str,
    risk_free_rate: float = 0.0,
    iv_unit: str = "DECIMAL",
    calculation_version: str = "black76-greeks-v1",
) -> Black76Greeks:
    F = float(futures_price)
    K = float(strike)
    T = float(expiry_years)
    sigma = normalize_iv(implied_volatility, iv_unit)

    if F <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        raise ValueError("INVALID_BLACK76_INPUT")

    d1, d2 = _d1_d2(F, K, sigma, T)
    discount = math.exp(-risk_free_rate * T)
    pdf = _N.pdf(d1)
    t = option_type.upper()

    direction = 1.0 if t == "CALL" else -1.0 if t == "PUT" else None
    if direction is None:
        raise ValueError(f"UNKNOWN_OPTION_TYPE:{option_type}")

    delta = discount * (direction * _N.cdf(direction * d1))
    gamma = discount * pdf / (F * sigma * math.sqrt(T))

    price = black76_option_price(
        F, K, sigma, T, t, risk_free_rate=risk_free_rate, iv_unit="DECIMAL"
    )

    theta = (
        risk_free_rate * price
        - discount * F * pdf * sigma / (2.0 * math.sqrt(T))
    )
    vega = discount * F * pdf * math.sqrt(T)

    return Black76Greeks(
        model="BLACK76",
        calculation_version=calculation_version,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        implied_volatility=sigma,
        iv_input_unit=iv_unit,
    )
