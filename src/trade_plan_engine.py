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

    htf = str(
        (state.get("decision") or {}).get("structural_bias")
        or (((state.get("decision_framework") or {}).get("steps") or {})
            .get("1_market_state") or {}).get("htf_structure")
        or "mixed"
    ).lower()
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
    """Build a deterministic conditional trade map.

    Four route objects are retained for backward compatibility, but the
    execution decision is reduced to:
      PRIMARY = route aligned with structural bias
      ALTERNATIVE = opposite-side contingency

    A trigger is a zone/event reference, not a literal fill price. An entry
    becomes executable only after the route-specific confirmation event and
    risk gate pass. This module never places orders.
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
        (state.get("decision") or {}).get("structural_bias")
        or (((state.get("decision_framework") or {}).get("steps") or {})
            .get("1_market_state") or {}).get("htf_structure")
        or "mixed"
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
        # Canonical market_map stores route targets as a source-derived list
        # (e.g. long_reclaim_trade_targets). Older payloads may expose tp1..tp5.
        values = [_n(market_map.get(f"{prefix}_tp{i}")) for i in range(1, 6)]
        if not any(v is not None for v in values):
            candidates = [
                market_map.get(f"{prefix}_trade_targets"),
                market_map.get(f"{prefix}_targets"),
                market_map.get(legacy_prefix) if legacy_prefix else None,
            ]
            for candidate in candidates:
                if isinstance(candidate, list):
                    values = [_n(x) for x in candidate[:5]]
                    if any(v is not None for v in values):
                        break
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
        # Canonicalize route targets before risk checks and rendering.
        # A stale/legacy payload may contain the trigger itself as TP1, targets
        # on the wrong side, duplicates, or unsorted nodes. Never invent a
        # replacement price: retain only valid source-derived nodes.
        is_long = str(side).upper().startswith("LONG")
        valid_targets = []
        for value in targets or []:
            target = _n(value)
            if target is None or trigger is None:
                continue
            if is_long and target <= trigger:
                continue
            if not is_long and target >= trigger:
                continue
            if target not in valid_targets:
                valid_targets.append(target)
        targets = sorted(valid_targets, reverse=not is_long)
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
        elif effective_state == "CONFIRMED":
            countertrend = (
                (htf == "bearish" and str(side).upper().startswith("LONG"))
                or (htf == "bullish" and str(side).upper().startswith("SHORT"))
            )
            if countertrend:
                effective_state = "COUNTERTREND_CONFIRMED"

        return {
            "side": side,
            "route": key,
            "entry_mode": "AFTER_CONFIRMATION",
            "entry_reference_role": "TRIGGER_ZONE_NOT_FILL",
            "execution_ready": bool(
                effective_state in {"CONFIRMED", "COUNTERTREND_CONFIRMED"}
                and risk.get("status") == "PASS"
            ),
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

    # Execution uses only the nearby levels prepared by the deterministic market map.
    long_reclaim_trigger = _n(market_map.get("long_reclaim_trigger"))
    long_support_trigger = _n(market_map.get("long_support_trigger"))
    short_rejection_trigger = _n(market_map.get("short_rejection_trigger"))
    short_breakdown_trigger = _n(market_map.get("short_breakdown_trigger"))

    long_reclaim_stop = _n(market_map.get("long_reclaim_stop")) if long_reclaim_trigger is not None else None
    long_support_stop = _n(market_map.get("long_support_invalidation")) if long_support_trigger is not None else None
    short_rejection_stop = _n(market_map.get("short_rejection_stop")) if short_rejection_trigger is not None else None
    short_breakdown_stop = _n(market_map.get("short_breakdown_stop")) if short_breakdown_trigger is not None else None

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
        # Read the route-specific canonical target arrays first. The previous
        # implementation read only legacy scalar fields for three routes, so
        # valid targets prepared by market_state were silently discarded.
        "long_reclaim": target_list("long_reclaim", "long_trade_targets"),
        "long_support": target_list("long_support"),
        "short_rejection": target_list("short_rejection"),
        "short_breakdown": target_list("short_breakdown"),
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
        "แตะโซนรับ → มีแรงตอบสนองราคา → M5 BOS ขึ้น → BUY",
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

    aligned_confirmed = []
    if htf == "bullish":
        aligned_confirmed = [
            route for route in (long_reclaim, long_support)
            if str(route.get("state") or "").upper() == "CONFIRMED"
        ]
    elif htf == "bearish":
        aligned_confirmed = [
            route for route in (short_rejection, short_breakdown)
            if str(route.get("state") or "").upper() == "CONFIRMED"
        ]

    if aligned_confirmed:
        overall = "CONFIRMED"
    elif any(str(x.get("state") or "").upper() == "COUNTERTREND_CONFIRMED" for x in routes):
        # A counter-trend route can be confirmed locally, but it must not
        # promote the global decision state against the H4/H1 context.
        overall = "COUNTERTREND_ROUTE_CONFIRMED"
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

    # Select the primary route from structural bias. Keep an alternative route
    # explicit, but never pretend it is simultaneously executable.
    def _pick_active(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        # Prefer a route that has actually reached its event/zone. This prevents
        # a dormant rejection route from hiding an already-triggered breakdown.
        active_states = {
            "CONFIRMED",
            "TRIGGERED_WAIT_CONFIRMATION",
            "TRIGGERED",
            "IN_ZONE",
            "APPROACHING",
            "ARMED",
        }
        return next((x for x in candidates if str(x.get("state") or "WAIT").upper() in active_states), candidates[0])

    if htf == "bearish":
        primary = _pick_active([short_rejection, short_breakdown])
        alternative = _pick_active([long_reclaim, long_support])
    elif htf == "bullish":
        primary = _pick_active([long_reclaim, long_support])
        alternative = _pick_active([short_rejection, short_breakdown])
    else:
        # Transition/mixed structure: show the route closest to an observable
        # event, but never promote it to a directional confirmation by itself.
        primary = _pick_active([short_rejection, short_breakdown, long_reclaim, long_support])
        alternative = (
            long_reclaim
            if str(primary.get("route")) in {"SELL_REJECTION", "SELL_BREAKDOWN"}
            else short_rejection
        )

    executable_primary = bool(primary.get("execution_ready"))
    executable_alternative = bool(alternative.get("execution_ready"))
    if executable_primary:
        permission = "ENTER_CONDITION_SATISFIED"
    elif primary.get("risk_blocked"):
        permission = "WAIT_RISK"
    elif primary.get("trigger") is None:
        permission = "WAIT_NO_ZONE"
    else:
        permission = "WAIT_CONFIRMATION"

    return {
        "version": "trade-plan-v4-two-scenario",
        "state": overall,
        "htf_context": htf,
        "current_price": current,
        "preferred_setup": primary.get("route") if primary else None,
        "preferred_action": primary.get("action") if primary else "รอให้เกิด Action ที่โซน",
        "primary_setup": primary,
        "alternative_setup": alternative,
        "trade_permission": permission,
        "execution_ready": executable_primary,
        "long": primary_long,
        "long_support": long_support,
        "short": primary_short,
        "long_reclaim": long_reclaim,
        "short_rejection": short_rejection,
        "short_breakdown": short_breakdown,
        "routes": routes,
        "rules": [
            "A structural zone is not an entry price.",
            "Entry becomes actionable only after route confirmation and risk gate pass.",
            "Primary follows H4/H1 structural bias; alternative is the contingency route.",
            "TP1-TP5 must come from source-derived structural nodes; missing levels stay UNKNOWN.",
            "No structural target means NO_TRADE rather than a fabricated price ladder.",
            "Risk failure blocks execution and renders WAIT/NO_TRADE.",
            "Counter-trend confirmation never promotes the global directional state.",
            "No order is placed by this module.",
        ],
    }
