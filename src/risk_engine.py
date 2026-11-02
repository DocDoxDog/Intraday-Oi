"""Deterministic setup risk and transaction-cost diagnostics.

Stop-noise calculations are advisory; they never override the existing risk gate.
"""
from __future__ import annotations

from typing import Any
import os

from src.quant_metrics import horizon_sigma, stop_touch_probability


def _n(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def stop_noise_assessment(
    risk_distance: float | None,
    iv_pct: float | None,
    price: float | None,
) -> dict[str, Any]:
    """Compare a stop with 1h/4h ATM-IV noise; not a forecast or win rate."""
    min_sigma = float(os.environ.get("MIN_STOP_SIGMA_1H", "1.5"))
    distance = _n(risk_distance)
    sigma_1h = horizon_sigma(price, iv_pct, 1.0)
    sigma_4h = horizon_sigma(price, iv_pct, 4.0)
    if distance is None or sigma_1h is None or sigma_1h <= 0:
        return {
            "status": "UNKNOWN",
            "reason": "missing_stop_distance_or_atm_iv",
            "warnings": [],
            "recommended_risk_scale": None,
        }
    multiple = distance / sigma_1h
    warnings = ["STOP_INSIDE_1H_NOISE"] if multiple < min_sigma else []
    touch_1h = stop_touch_probability(distance, sigma_1h)
    touch_4h = stop_touch_probability(distance, sigma_4h) if sigma_4h else None
    return {
        "status": "OK",
        "sigma_1h": round(sigma_1h, 4),
        "sigma_4h": round(sigma_4h, 4) if sigma_4h is not None else None,
        "stop_sigma_multiple_1h": round(multiple, 4),
        "touch_probability_1h": round(touch_1h, 4) if touch_1h is not None else None,
        "touch_probability_4h": round(touch_4h, 4) if touch_4h is not None else None,
        "min_stop_sigma_1h": min_sigma,
        "recommended_risk_scale": round(min(1.0, multiple / min_sigma), 3),
        "warnings": warnings,
        "model": "driftless_reflection_principle_atm_iv_trading_time",
        "limitation": "Advisory barrier-touch estimate; assumes zero drift and constant volatility.",
    }


def evaluate_setup_risk(
    side: str,
    entry: float | None,
    stop: float | None,
    targets: list[float | None],
    *,
    atr: float | None = None,
    spread: float | None = None,
    slippage: float | None = None,
    min_rr: float | None = None,
    max_stop_atr: float | None = None,
    iv_pct: float | None = None,
    ref_price: float | None = None,
) -> dict[str, Any]:
    min_rr = float(os.environ.get("MIN_RR1", "1.0")) if min_rr is None else min_rr
    max_stop_atr = float(os.environ.get("MAX_STOP_ATR_MULTIPLE", "3.0")) if max_stop_atr is None else max_stop_atr
    entry_value, stop_value = _n(entry), _n(stop)
    is_long = str(side).upper().startswith("LONG")
    if entry_value is None or stop_value is None:
        return {"status": "NO_TRADE", "reason": "MISSING_ENTRY_OR_STOP"}
    risk = entry_value - stop_value if is_long else stop_value - entry_value
    if risk <= 0:
        return {"status": "NO_TRADE", "reason": "INVALID_STOP_DIRECTION"}

    gross = []
    for target in targets:
        target_value = _n(target)
        if target_value is None:
            continue
        reward = target_value - entry_value if is_long else entry_value - target_value
        gross.append(round(reward / risk, 2) if reward > 0 else None)
    rr1 = gross[0] if gross else None
    if rr1 is None:
        return {"status": "NO_TRADE", "reason": "NO_QUALIFIED_TP1", "risk_distance": round(risk, 5), "rr": []}
    if rr1 < min_rr:
        return {"status": "NO_TRADE", "reason": "RR_BELOW_MIN", "risk_distance": round(risk, 5), "rr": gross, "rr1": rr1}
    if atr is not None and atr > 0 and risk > max_stop_atr * atr:
        return {
            "status": "NO_TRADE",
            "reason": "STOP_TOO_FAR",
            "risk_distance": round(risk, 5),
            "atr": atr,
            "max_stop_atr_multiple": max_stop_atr,
            "rr": gross,
        }

    cost = None
    if spread is not None or slippage is not None:
        cost = max(0.0, _n(spread) or 0.0) + max(0.0, _n(slippage) or 0.0)
    cost_adjusted_rr = []
    for index, target in enumerate(targets):
        ratio = gross[index] if index < len(gross) else None
        target_value = _n(target)
        if ratio is None or cost is None or target_value is None:
            cost_adjusted_rr.append(None)
            continue
        reward = target_value - entry_value if is_long else entry_value - target_value
        cost_adjusted_rr.append(round(max(0.0, reward - cost) / (risk + cost), 2))

    noise = stop_noise_assessment(
        risk,
        iv_pct,
        ref_price if ref_price is not None else entry_value,
    )
    warnings = list(noise.get("warnings") or [])
    cost_rr1 = cost_adjusted_rr[0] if cost_adjusted_rr else None
    if cost_rr1 is not None and cost_rr1 < min_rr:
        warnings.append("RR1_BELOW_MIN_AFTER_COSTS")

    return {
        "status": "PASS",
        "reason": "RISK_QUALIFIED",
        "risk_distance": round(risk, 5),
        "rr": gross,
        "rr1": rr1,
        "cost_per_roundtrip": cost,
        "cost_adjusted_rr": cost_adjusted_rr,
        "max_stop_atr_multiple": max_stop_atr,
        "stop_noise": noise,
        "warnings": warnings,
        "recommended_risk_scale": noise.get("recommended_risk_scale"),
    }
