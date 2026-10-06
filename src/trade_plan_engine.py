"""Deterministic conditional trade-plan state machine.

The analyst proposes context; this module decides whether a setup is merely armed,
has triggered, or is confirmed. It never places an order.
"""
from __future__ import annotations

from typing import Any


def _n(v: Any) -> float | None:
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _trend(state: dict[str, Any], tf: str) -> str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("trend") or "").lower()


def _bos(state: dict[str, Any], tf: str) -> str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("bos") or "").lower()


def _momentum(state: dict[str, Any], tf: str) -> float | None:
    return _n(((state.get("technical") or {}).get(tf) or {}).get("momentum_5"))


def _side_confirmation(state: dict[str, Any], side: str, current: float | None, trigger: float | None) -> dict[str, Any]:
    if current is None or trigger is None:
        return {"state": "DATA_INSUFFICIENT", "conditions": []}

    htf = str((((state.get("decision_framework") or {}).get("steps") or {}).get("1_market_state") or {}).get("htf_structure") or "mixed").lower()
    if side == "LONG":
        aligned = htf == "bullish" and _trend(state, "m15") == "bullish" and _trend(state, "m5") == "bullish"
        bos_ok = _bos(state, "m5") in {"bullish", "bull", "up", "bos_up", "break_up"}
        momentum = _momentum(state, "m5")
        location = current > trigger
        conditions = [
            "htf_bullish" if htf == "bullish" else "htf_not_bullish",
            "price_above_trigger" if location else "waiting_break_above_trigger",
            "m15_bullish" if _trend(state, "m15") == "bullish" else "m15_not_bullish",
            "m5_bullish" if _trend(state, "m5") == "bullish" else "m5_not_bullish",
            "m5_bos_bullish" if bos_ok else "m5_bos_not_confirmed",
        ]
        if location and aligned and bos_ok:
            return {"state": "CONFIRMED", "conditions": conditions, "momentum": momentum}
        if location:
            return {"state": "TRIGGERED_WAIT_CONFIRMATION", "conditions": conditions, "momentum": momentum}
        return {"state": "ARMED", "conditions": conditions, "momentum": momentum}

    aligned = htf == "bearish" and _trend(state, "m15") == "bearish" and _trend(state, "m5") == "bearish"
    bos_ok = _bos(state, "m5") in {"bearish", "bear", "down", "bos_down", "break_down"}
    momentum = _momentum(state, "m5")
    location = current < trigger
    conditions = [
        "htf_bearish" if htf == "bearish" else "htf_not_bearish",
        "price_below_trigger" if location else "waiting_break_below_trigger",
        "m15_bearish" if _trend(state, "m15") == "bearish" else "m15_not_bearish",
        "m5_bearish" if _trend(state, "m5") == "bearish" else "m5_not_confirmed",
        "m5_bos_bearish" if bos_ok else "m5_bos_not_confirmed",
    ]
    if location and aligned and bos_ok:
        return {"state": "CONFIRMED", "conditions": conditions, "momentum": momentum}
    if location:
        return {"state": "TRIGGERED_WAIT_CONFIRMATION", "conditions": conditions, "momentum": momentum}
    return {"state": "ARMED", "conditions": conditions, "momentum": momentum}


def _risk_reward(side: str, entry: float | None, stop: float | None, tp: float | None) -> float | None:
    if None in (entry, stop, tp):
        return None
    risk = entry - stop if side == "LONG" else stop - entry
    reward = tp - entry if side == "LONG" else entry - tp
    if risk <= 0 or reward <= 0:
        return None
    return round(reward / risk, 2)


def build_trade_execution_plan(state: dict[str, Any]) -> dict[str, Any]:
    """Build executable conditions from the canonical market state.

    Prices remain source-derived. The state machine is the only component that
    can promote a conditional setup to CONFIRMED.
    """
    levels = state.get("levels") or {}
    current = _n((state.get("price") or {}).get("cfd"))
    long_trigger = _n(levels.get("resistance_current"))
    short_trigger = _n(levels.get("support_current"))

    market = state.get("decision_framework") or {}
    htf = (((market.get("steps") or {}).get("1_market_state") or {}).get("htf_structure") or "mixed").lower()

    long_stop = _n(levels.get("support_main"))
    short_stop = _n(levels.get("resistance_main"))

    # Targets are supplied by the deterministic market map after validation.
    market_map = state.get("market_map") or {}
    long_targets = [_n(market_map.get(k)) for k in ("R1", "R2", "R3")]
    short_targets = [_n(market_map.get(k)) for k in ("S1", "S2", "S3")]

    long_conf = _side_confirmation(state, "LONG", current, long_trigger)
    short_conf = _side_confirmation(state, "SHORT", current, short_trigger)

    def side_payload(side: str, trigger: float | None, stop: float | None, targets: list[float | None], conf: dict[str, Any]) -> dict[str, Any]:
        rr = [_risk_reward(side, trigger, stop, x) for x in targets]
        risk_per_unit = abs(trigger - stop) if trigger is not None and stop is not None else None
        rr1_ok = rr[0] is not None and rr[0] >= 1.0
        effective_state = conf["state"]
        if effective_state == "CONFIRMED" and not rr1_ok:
            effective_state = "TRIGGERED_WAIT_RISK_REWARD"
        return {
            "side": side,
            "state": effective_state,
            "trigger": trigger,
            "entry_reference": trigger,
            "stop": stop,
            "targets": targets,
            "rr": rr,
            "risk_per_unit": risk_per_unit,
            "minimum_rr1": 1.0,
            "rr1_eligible": rr1_ok,
            "confirmation": conf["conditions"],
            "position_sizing": "risk_budget / abs(entry_reference - stop); execution engine applies contract value, tick size and max-risk limits",
            "cancel_if": (
                "HTF structure invalidates thesis or trigger is reclaimed before confirmation"
                if side == "SHORT"
                else "HTF structure invalidates thesis or trigger is lost before confirmation"
            ),
            "execution_authority": "NONE",
        }

    # A confirmed side is still only a research signal; Ai-trader must enforce
    # portfolio risk and broker constraints before execution.
    long_payload = side_payload("LONG", long_trigger, long_stop, long_targets, long_conf)
    short_payload = side_payload("SHORT", short_trigger, short_stop, short_targets, short_conf)
    status = "CONFIRMED" if long_payload["state"] == "CONFIRMED" or short_payload["state"] == "CONFIRMED" else (
        "TRIGGERED" if long_conf["state"] == "TRIGGERED_WAIT_CONFIRMATION" or short_conf["state"] == "TRIGGERED_WAIT_CONFIRMATION" else "ARMED"
    )

    return {
        "version": "trade-plan-v2",
        "state": status,
        "htf_context": htf,
        "current_price": current,
        "long": long_payload,
        "short": short_payload,
        "rules": [
            "Trigger is a structural level; touching it is not confirmation.",
            "Confirmation requires price beyond trigger plus M15/M5 alignment and M5 BOS confirmation.",
            "Stop is structural invalidation; position size must be derived from actual risk budget.",
            "Targets are source-derived levels only; missing targets remain UNKNOWN.",
            "No order is placed by this module.",
        ],
    }
