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
    """Build the complete four-route trade map.

    Every route is visible at the same time:
      BUY 1 = resistance breakout / reclaim
      BUY 2 = support reaction
      SELL 1 = resistance rejection / failed retest
      SELL 2 = support breakdown / retest failure

    The selected market bias changes priority, not the existence of the
    alternative plans. No route places an order.
    """
    market_map = state.get("market_map") or {}
    levels = state.get("levels") or {}
    current = _n((state.get("price") or {}).get("cfd"))
    technical = state.get("technical") or {}
    atr = _n(((technical.get("m5") or {}).get("atr14")))
    flow = state.get("order_flow") or {}
    book = flow.get("book") or {}
    spread = _n(book.get("spread"))

    action_zones = state.get("action_zones") or {}
    setups = action_zones.get("setups") or {}

    htf = str(
        (((state.get("decision_framework") or {}).get("steps") or {})
         .get("1_market_state") or {}).get("htf_structure") or "mixed"
    ).lower()

    def fallback_confirmation(side: str, trigger: float | None) -> dict[str, Any]:
        return _side_confirmation(state, side, current, trigger)

    def zone_confirmation(key: str, side: str, trigger: float | None) -> dict[str, Any]:
        setup = setups.get(key)
        if isinstance(setup, dict):
            result = confirm_setup(setup, state)
            result["zone_state"] = setup.get("state")
            result["event_required"] = setup.get("event_required")
            result["action"] = setup.get("action")
            result["invalidation"] = setup.get("invalidation")
            return result
        return fallback_confirmation(side, trigger)

    def target_list(prefix: str, legacy_prefix: str | None = None) -> list[float | None]:
        values = [_n(market_map.get(f"{prefix}_tp{i}")) for i in range(1, 6)]
        if not any(v is not None for v in values) and legacy_prefix:
            legacy = market_map.get(legacy_prefix)
            if isinstance(legacy, list):
                values = [_n(x) for x in legacy[:5]]
        return values

    def side_payload(
        key: str,
        title: str,
        strategy: str,
        side: str,
        trigger: float | None,
        stop: float | None,
        targets: list[float | None],
        conf: dict[str, Any],
        action: str,
        cancel_if: str,
    ) -> dict[str, Any]:
        rr = [_risk_reward(side, trigger, stop, x) for x in targets]
        risk_per_unit = abs(trigger - stop) if trigger is not None and stop is not None else None
        rr1_ok = bool(rr) and rr[0] is not None and rr[0] >= 1.0
        effective_state = str(conf.get("state") or "WAIT")
        risk = evaluate_setup_risk(
            side, trigger, stop, targets,
            atr=atr, spread=spread, slippage=None,
        )

        risk_blocked = risk.get("status") != "PASS"
        if effective_state == "CONFIRMED" and risk_blocked:
            effective_state = "NO_TRADE"

        return {
            "side": side,
            "route": key,
            "title": title,
            "strategy": strategy,
            "state": effective_state,
            "trigger": trigger,
            "entry_reference": trigger,
            "stop": stop,
            "targets": targets,
            "rr": rr,
            "risk_per_unit": risk_per_unit,
            "minimum_rr1": 1.0,
            "rr1_eligible": rr1_ok,
            "risk": risk,
            "risk_blocked": risk_blocked,
            "action": action,
            "confirmation": conf.get("conditions") or conf.get("checks") or [],
            "event_required": conf.get("event_required"),
            "zone_state": conf.get("zone_state"),
            "cancel_if": cancel_if,
            "position_sizing": "risk_budget / abs(entry_reference - stop); downstream execution engine applies contract value, tick size and max-risk limits",
            "execution_authority": "NONE",
        }

    # Explicit four route inputs. These come from the deterministic market map
    # and are never fabricated by the LLM.
    long_reclaim_trigger = _n(market_map.get("long_reclaim_trigger")) or _n(market_map.get("call_wall")) or _n(levels.get("resistance_main"))
    long_support_trigger = _n(market_map.get("long_support_trigger")) or _n(market_map.get("put_wall")) or _n(levels.get("support_main"))
    short_rejection_trigger = _n(market_map.get("short_rejection_trigger")) or _n(market_map.get("call_wall")) or _n(levels.get("resistance_main"))
    short_breakdown_trigger = _n(market_map.get("short_breakdown_trigger")) or _n(market_map.get("put_wall")) or _n(levels.get("support_main"))

    long_reclaim_stop = _n(market_map.get("long_reclaim_stop")) or _n(market_map.get("long_invalidation"))
    long_support_stop = _n(market_map.get("long_support_invalidation"))
    short_rejection_stop = _n(market_map.get("short_rejection_stop"))
    short_breakdown_stop = _n(market_map.get("short_breakdown_stop")) or _n(market_map.get("short_invalidation"))

    long_reclaim_conf = zone_confirmation("breakout_retest_long", "LONG", long_reclaim_trigger)
    long_support_conf = zone_confirmation("reversal_long", "LONG", long_support_trigger)
    short_rejection_conf = zone_confirmation("reversal_short", "SHORT", short_rejection_trigger)
    short_breakdown_conf = zone_confirmation("breakout_retest_short", "SHORT", short_breakdown_trigger)

    # Support reaction is only allowed after the market actually reaches the
    # lower zone. A higher price being technically bullish is not a buy-at-
    # support confirmation.
    if (
        long_support_conf.get("state") == "CONFIRMED"
        and current is not None
        and long_support_trigger is not None
        and current > long_support_trigger
    ):
        long_support_conf["state"] = "ARMED"
        long_support_conf.setdefault("conditions", []).append("waiting_support_reaction")

    target_map = {
        "long_reclaim": target_list("long_reclaim", "long_trade_targets"),
        "long_support": [_n(market_map.get(f"long_support_tp{i}")) for i in range(1, 6)],
        "short_rejection": [_n(market_map.get(f"short_rejection_tp{i}")) for i in range(1, 6)] or [_n(x) for x in (market_map.get("short_trade_targets") or [])[:5]],
        "short_breakdown": [_n(market_map.get(f"short_breakdown_tp{i}")) for i in range(1, 6)],
    }

    long_reclaim = side_payload(
        "BUY_BREAKOUT",
        "BUY — เบรกต้าน",
        "BREAKOUT_RETEST",
        "LONG",
        long_reclaim_trigger,
        long_reclaim_stop,
        target_map["long_reclaim"],
        long_reclaim_conf,
        "เบรกและยืนเหนือโซน → รีเทสต์ไม่หลุด → BUY",
        "ยืนกลับใต้ breakout zone ก่อน confirmation",
    )
    long_support = side_payload(
        "BUY_SUPPORT",
        "BUY — รับด้านล่าง",
        "REVERSAL",
        "LONG_SUPPORT",
        long_support_trigger,
        long_support_stop,
        target_map["long_support"],
        long_support_conf,
        "แตะโซนรับ → rejection/absorption → M5 BOS ขึ้น → BUY",
        "รับไม่อยู่ / ยอมรับราคาต่ำกว่า support",
    )
    short_rejection = side_payload(
        "SELL_REJECTION",
        "SELL — ต้านไม่ผ่าน",
        "REVERSAL / FAILED_RETEST",
        "SHORT",
        short_rejection_trigger,
        short_rejection_stop,
        target_map["short_rejection"],
        short_rejection_conf,
        "เด้งกลับต้าน → rejection → M5 BOS ลง → SELL",
        "ยืนเหนือ resistance และรับราคาได้",
    )
    short_breakdown = side_payload(
        "SELL_BREAKDOWN",
        "SELL — หลุดแนวรับ",
        "BREAKOUT_RETEST",
        "SHORT",
        short_breakdown_trigger,
        short_breakdown_stop,
        target_map["short_breakdown"],
        short_breakdown_conf,
        "หลุดแนวรับ → รีเทสต์ไม่ผ่าน → M5 BOS ลง → SELL",
        "กลับขึ้นเหนือ breakdown zone",
    )

    # Compatibility aliases: existing Telegram/dashboard consumers can still
    # use long / long_support / short, while the four explicit routes are
    # canonical for the new UI.
    primary_short = short_rejection if htf == "bearish" else short_breakdown
    primary_long = long_reclaim if htf == "bullish" else long_support

    routes = [long_reclaim, long_support, short_rejection, short_breakdown]
    states = [str(x.get("state") or "WAIT").upper() for x in routes]

    if "CONFIRMED" in states:
        overall = "CONFIRMED"
    elif any(x in states for x in {"TRIGGERED_WAIT_CONFIRMATION", "TRIGGERED", "TRIGGERED_WAIT_RISK_REWARD"}):
        overall = "TRIGGERED"
    elif any(x in states for x in {"IN_ZONE", "APPROACHING", "ARMED"}):
        overall = "ARMED"
    elif all(x in {"NO_TRADE", "WAIT", "DATA_INSUFFICIENT", "INVALIDATED"} for x in states):
        risk_ready = any(bool(route.get("trigger") is not None and route.get("stop") is not None) for route in routes)
        overall = "NO_TRADE" if risk_ready else "DATA_INSUFFICIENT"
    else:
        overall = "WAIT"

    if overall == "CONFIRMED":
        priority = [x for x in routes if x.get("state") == "CONFIRMED"]
    elif htf == "bearish":
        priority = [short_rejection, short_breakdown, long_support, long_reclaim]
    elif htf == "bullish":
        priority = [long_reclaim, long_support, short_rejection, short_breakdown]
    else:
        priority = [long_reclaim, long_support, short_rejection, short_breakdown]

    preferred = next((x for x in priority if x.get("state") not in {"WAIT", "NO_TRADE", "INVALIDATED", "DATA_INSUFFICIENT"}), priority[0])

    return {
        "version": "trade-plan-v3-four-routes",
        "state": overall,
        "htf_context": htf,
        "current_price": current,
        "preferred_setup": preferred.get("route"),
        "preferred_action": preferred.get("action"),
        "long": primary_long,
        "long_support": long_support,
        "short": primary_short,
        "long_reclaim": long_reclaim,
        "short_rejection": short_rejection,
        "short_breakdown": short_breakdown,
        "routes": routes,
        "rules": [
            "Price touching a level is not an entry.",
            "Each route requires its own market event and confirmation.",
            "TP1-TP5 are source-derived structural levels; missing levels stay UNKNOWN.",
            "Risk failure blocks confirmation and must render NO TRADE.",
            "Directional bias changes priority, not the availability of the opposite setup.",
            "No order is placed by this module.",
        ],
    }
