"""Deterministic conditional trade-plan state machine.

The analyst proposes context; this module decides whether a setup is merely armed,
has triggered, or is confirmed. It never places an order.
"""
from __future__ import annotations

from typing import Any

from src.confirmation_engine import confirm_setup
from src.risk_engine import evaluate_setup_risk


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
        location = current >= trigger
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
    location = current <= trigger
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
    is_long = str(side).upper().startswith("LONG")
    risk = entry - stop if is_long else stop - entry
    reward = tp - entry if is_long else entry - tp
    if risk <= 0 or reward <= 0:
        return None
    return round(reward / risk, 2)


def build_trade_execution_plan(state: dict[str, Any]) -> dict[str, Any]:
    """Build executable conditions from the canonical market state.

    Prices remain source-derived. The state machine is the only component that
    can promote a conditional setup to CONFIRMED.
    """
    levels = state.get("levels") or {}
    market_map = state.get("market_map") or {}
    current = _n((state.get("price") or {}).get("cfd"))
    long_trigger = _n(market_map.get("long_trigger")) or _n(levels.get("resistance_current"))
    short_trigger = _n(market_map.get("short_trigger")) or _n(levels.get("support_current"))

    market = state.get("decision_framework") or {}
    htf = (((market.get("steps") or {}).get("1_market_state") or {}).get("htf_structure") or "mixed").lower()

    long_stop = _n(market_map.get("long_invalidation")) or _n(levels.get("support_main"))
    short_stop = _n(market_map.get("short_invalidation")) or _n(levels.get("resistance_main"))

    # R/S are structural key levels. Execution targets are a separate,
    # risk-qualified layer and must never be inferred from R/S automatically.
    long_targets = [_n(x) for x in (market_map.get("long_trade_targets") or [])]
    long_support_trigger = _n(market_map.get("long_support_trigger"))
    long_support_stop = _n(market_map.get("long_support_invalidation"))
    long_support_targets = [_n(x) for x in (market_map.get("long_support_trade_targets") or [])]
    short_targets = [_n(x) for x in (market_map.get("short_trade_targets") or [])]

    # Action Zone Engine is the preferred semantic gate. Keep the old
    # confirmation function as a compatibility fallback for snapshots that do
    # not yet contain action_zones.
    action_zones = state.get("action_zones") or {}
    setups = action_zones.get("setups") or {}

    def _zone_confirmation(key: str, fallback_side: str, trigger: float | None) -> dict[str, Any]:
        setup = setups.get(key)
        if isinstance(setup, dict):
            result = confirm_setup(setup, state)
            result["zone_state"] = setup.get("state")
            result["event_required"] = setup.get("event_required")
            return result
        return _side_confirmation(state, fallback_side, current, trigger)

    long_conf = _zone_confirmation("breakout_retest_long", "LONG", long_trigger)
    short_conf = _zone_confirmation("breakout_retest_short", "SHORT", short_trigger)

    # Support-reaction LONG: price reaches the lower structural zone, then
    # requires bullish M15/M5 confirmation and M5 BOS. This is an alternative
    # setup, not an automatic BUY merely because OI/volume is large.
    support_setup = setups.get("reversal_long")
    if isinstance(support_setup, dict):
        long_support_conf = confirm_setup(support_setup, state)
        long_support_conf["zone_state"] = support_setup.get("state")
        long_support_conf["event_required"] = support_setup.get("event_required")
    else:
        long_support_conf = _side_confirmation(
            state,
            "LONG",
            current,
            long_support_trigger,
        )
    if long_support_conf["state"] == "CONFIRMED" and current is not None and long_support_trigger is not None and current > long_support_trigger:
        long_support_conf["state"] = "ARMED"
        if "conditions" in long_support_conf:
            long_support_conf["conditions"].append("waiting_support_reaction")
        elif "checks" in long_support_conf:
            long_support_conf["checks"].append({"name": "waiting_support_reaction", "pass": False})

    def side_payload(side: str, trigger: float | None, stop: float | None, targets: list[float | None], conf: dict[str, Any]) -> dict[str, Any]:
        rr = [_risk_reward(side, trigger, stop, x) for x in targets]
        risk_per_unit = abs(trigger - stop) if trigger is not None and stop is not None else None
        rr1_ok = bool(rr) and rr[0] is not None and rr[0] >= 1.0
        effective_state = conf["state"]
        if effective_state == "CONFIRMED" and not rr1_ok:
            effective_state = "TRIGGERED_WAIT_RISK_REWARD"
        technical = state.get("technical") or {}
        atr = _n(((technical.get("m5") or {}).get("atr14")))
        flow = state.get("order_flow") or {}
        book = flow.get("book") or {}
        spread = _n(book.get("spread"))
        risk = evaluate_setup_risk(
            side, trigger, stop, targets,
            atr=atr, spread=spread, slippage=None,
        )
        if effective_state == "CONFIRMED" and risk.get("status") != "PASS":
            effective_state = "NO_TRADE"
        elif effective_state == "TRIGGERED_WAIT_RISK_REWARD" and risk.get("status") == "NO_TRADE":
            effective_state = "NO_TRADE"
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
            "confirmation": conf.get("conditions") or conf.get("checks") or [],
            "zone_state": conf.get("zone_state"),
            "event_required": conf.get("event_required"),
            "risk": risk,
            "position_sizing": "risk_budget / abs(entry_reference - stop); downstream execution engine applies contract value, tick size and max-risk limits",
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
    long_support_payload = side_payload(
        "LONG_SUPPORT",
        long_support_trigger,
        long_support_stop,
        long_support_targets,
        long_support_conf,
    )
    short_payload = side_payload("SHORT", short_trigger, short_stop, short_targets, short_conf)
    if long_payload["state"] == "CONFIRMED" or long_support_payload["state"] == "CONFIRMED" or short_payload["state"] == "CONFIRMED":
        status = "CONFIRMED"
    elif (
        long_payload["state"] in {"TRIGGERED_WAIT_CONFIRMATION", "TRIGGERED_WAIT_RISK_REWARD"}
        or long_support_payload["state"] in {"TRIGGERED_WAIT_CONFIRMATION", "TRIGGERED_WAIT_RISK_REWARD"}
        or short_payload["state"] in {"TRIGGERED_WAIT_CONFIRMATION", "TRIGGERED_WAIT_RISK_REWARD"}
    ):
        status = "TRIGGERED"
    elif long_payload["state"] == "ARMED" or short_payload["state"] == "ARMED":
        status = "ARMED"
    else:
        status = "DATA_INSUFFICIENT"

    return {
        "version": "trade-plan-v2",
        "state": status,
        "htf_context": htf,
        "current_price": current,
        "long": long_payload,
        "long_support": long_support_payload,
        "short": short_payload,
        "rules": [
            "Reaching a structural trigger moves the setup to TRIGGERED; it is not confirmation.",
            "Confirmation requires trigger reached plus M15/M5 alignment and M5 BOS confirmation.",
            "Stop is structural invalidation; position size must be derived from actual risk budget.",
            "Targets are source-derived levels only; missing targets remain UNKNOWN.",
            "No order is placed by this module.",
        ],
    }
