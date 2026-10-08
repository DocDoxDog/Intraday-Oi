"""Canonical evidence → decision synthesis for Intraday-Oi.

This module is the single deterministic decision boundary between raw market
evidence and customer-facing directional language.

Design principles:
- Structure defines the directional context.
- M5/M15 define tactical direction and price confirmation.
- Options (OI/IV/GEX) explain the mechanism; they do not override price.
- A level is not a trigger; a trigger is not confirmation.
- Missing/conflicting evidence resolves to WAIT/DEVELOPING.
- No opaque score/probability is produced.
"""
from __future__ import annotations

from typing import Any


LONG_BOS = {"bullish", "bull", "up", "bos_up", "bullish_bos", "break_up"}
SHORT_BOS = {"bearish", "bear", "down", "bos_down", "bearish_bos", "break_down"}


def _n(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trend(state: dict[str, Any], tf: str) -> str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("trend") or "").lower()


def _bos(state: dict[str, Any], tf: str) -> str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("bos") or "").lower()


def _fresh_high_news(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in state.get("news") or []
        if isinstance(item, dict)
        and str(item.get("freshness") or "").upper() in {"FRESH", "RECENT"}
        and str(item.get("relevance") or "").upper() in {"HIGH", "CRITICAL"}
    ]


def _structural_bias(state: dict[str, Any]) -> str:
    h4, h1 = _trend(state, "h4"), _trend(state, "h1")
    if h4 == h1 == "bullish":
        return "BULLISH"
    if h4 == h1 == "bearish":
        return "BEARISH"
    return "MIXED"


def _tactical_direction(state: dict[str, Any], structural_bias: str) -> str:
    m15, m5 = _trend(state, "m15"), _trend(state, "m5")
    tactical = m5 if m5 in {"bullish", "bearish"} else m15 if m15 in {"bullish", "bearish"} else "neutral"
    if structural_bias == "MIXED":
        return f"{tactical.upper()}_TRANSITION" if tactical != "neutral" else "NEUTRAL_TRANSITION"
    if tactical == structural_bias.lower():
        return f"{tactical.upper()}_ALIGNED"
    if tactical in {"bullish", "bearish"}:
        return f"{tactical.upper()}_AGAINST_STRUCTURE"
    return "NEUTRAL"


def _gamma_context(state: dict[str, Any]) -> str:
    net_gex = _n((state.get("gamma") or {}).get("net_gex"))
    if net_gex is None:
        return "UNKNOWN"
    if net_gex > 0:
        return "POSITIVE_GAMMA_DAMPENING_CONTEXT"
    if net_gex < 0:
        return "NEGATIVE_GAMMA_AMPLIFICATION_CONTEXT"
    return "NEUTRAL_GAMMA_CONTEXT"


def _oi_context(state: dict[str, Any]) -> dict[str, Any]:
    flow = state.get("flow") or {}
    put_change = _n(flow.get("oi_change_put"))
    call_change = _n(flow.get("oi_change_call"))
    if put_change is None and call_change is None:
        activity = "UNKNOWN"
    elif put_change is not None and call_change is not None and put_change > 0 and call_change > 0:
        activity = "TWO_SIDED_BUILD"
    elif put_change is not None and call_change is not None and put_change < 0 and call_change < 0:
        activity = "TWO_SIDED_REDUCTION"
    else:
        activity = "MIXED_ACTIVITY"
    return {
        "activity": activity,
        "put_change": put_change,
        "call_change": call_change,
        "aggressor_direction": "UNKNOWN",
        "limitation": "OI/ΔOI/churn describe positioning activity; they do not identify aggressor direction.",
    }


def _volatility_context(state: dict[str, Any]) -> dict[str, Any]:
    vol = state.get("volatility") or {}
    iv = _n(vol.get("iv"))
    iv_change = _n(vol.get("iv_change_1h"))
    if iv_change is None:
        movement = "UNKNOWN"
    elif iv_change > 0:
        movement = "EXPANDING"
    elif iv_change < 0:
        movement = "COMPRESSING"
    else:
        movement = "STABLE"

    # No percentile/week baseline exists in the canonical state today.
    # Therefore this engine intentionally refuses to call IV "high" or "low".
    return {
        "iv": iv,
        "iv_change_1h": iv_change,
        "movement": movement,
        "level_assessment": "CURRENT_ONLY_BASELINE_UNAVAILABLE",
        "term_structure": vol.get("iv_term_structure") or [],
        "skew": _n(vol.get("skew")),
    }


def _action_trigger(state: dict[str, Any], side: str) -> float | None:
    setups = ((state.get("action_zones") or {}).get("setups") or {})
    key = "breakout_retest_long" if side == "LONG" else "breakout_retest_short"
    setup = setups.get(key) or {}
    zone = _n(setup.get("zone_price"))
    if zone is not None:
        return zone
    levels = state.get("levels") or {}
    return _n(levels.get("resistance_current" if side == "LONG" else "support_current"))


def _location(state: dict[str, Any]) -> str:
    price = state.get("price") or {}
    current = _n(price.get("cfd"))
    resistance = _action_trigger(state, "LONG")
    support = _action_trigger(state, "SHORT")
    if current is None or resistance is None or support is None:
        return "UNKNOWN"
    if current >= resistance:
        return "ABOVE_RESISTANCE"
    if current <= support:
        return "BELOW_SUPPORT"
    return "INSIDE_STRUCTURE"


def _route_confirmations(
    state: dict[str, Any],
    side: str,
    structural_bias: str,
) -> dict[str, Any]:
    """Reuse the canonical route confirmation engine for global confirmation."""
    from src.confirmation_engine import confirm_setup

    if side == "LONG":
        route_keys = ("breakout_retest_long", "reversal_long")
        allowed = structural_bias == "BULLISH"
    else:
        route_keys = ("breakout_retest_short", "reversal_short")
        allowed = structural_bias == "BEARISH"

    setups = ((state.get("action_zones") or {}).get("setups") or {})
    routes: list[dict[str, Any]] = []
    for key in route_keys:
        setup = setups.get(key)
        if not isinstance(setup, dict):
            continue
        result = confirm_setup(setup, state)
        routes.append({
            "route": key,
            "zone_state": setup.get("state"),
            "trigger": _n(setup.get("zone_price")),
            "state": result.get("state", "WAIT"),
            "confirmed": bool(result.get("confirmed")) and allowed,
            "route_confirmed": bool(result.get("confirmed")),
            "conditions": result.get("checks") or [],
            "event_required": result.get("event_required") or setup.get("event_required"),
            "action": result.get("action") or setup.get("action"),
        })

    if not routes:
        return {
            "state": "DATA_INSUFFICIENT",
            "confirmed": False,
            "route": None,
            "routes": [],
            "conditions": ["no_action_zone_confirmation_route"],
        }

    confirmed = next((x for x in routes if x["confirmed"]), None)
    triggered = next(
        (x for x in routes if x["state"] in {"TRIGGERED_WAIT_CONFIRMATION", "TRIGGERED"}),
        None,
    )
    active = confirmed or triggered or routes[0]
    if confirmed:
        global_state = "CONFIRMED"
    elif triggered:
        global_state = "TRIGGERED_WAIT_CONFIRMATION"
    else:
        global_state = str(active.get("state") or "WAIT")

    return {
        "state": global_state,
        "confirmed": bool(confirmed),
        "route": active.get("route"),
        "trigger": active.get("trigger"),
        "conditions": active.get("conditions") or [],
        "event_required": active.get("event_required"),
        "action": active.get("action"),
        "routes": routes,
        "structure_aligned": allowed,
    }



def _what_would_confirm(structural_bias: str, state: dict[str, Any]) -> dict[str, list[str]]:
    resistance = _action_trigger(state, "LONG")
    support = _action_trigger(state, "SHORT")

    bull = [
        f"ราคายืนเหนือ {_fmt(resistance)} และผ่านการทดสอบซ้ำ" if resistance is not None else "ราคาทะลุแนวต้านและยืนได้",
        "M15/M5 เปลี่ยนเป็น bullish สอดคล้องกับโครงสร้าง",
        "M5 มี bullish BOS ที่สังเกตได้",
    ]
    bear = [
        f"ราคาหลุด {_fmt(support)} และกลับมาทดสอบแล้วไม่ผ่าน" if support is not None else "ราคาหลุดแนวรับและรีเทสต์ไม่ผ่าน",
        "M15/M5 เปลี่ยนเป็น bearish สอดคล้องกับโครงสร้าง",
        "M5 มี bearish BOS ที่สังเกตได้",
    ]
    if structural_bias == "BULLISH":
        bull.insert(0, "โครงสร้าง H4/H1 ยังคง bullish")
    elif structural_bias == "BEARISH":
        bear.insert(0, "โครงสร้าง H4/H1 ยังคง bearish")
    return {"BULLISH": bull, "BEARISH": bear}


def _fmt(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None else "ระดับที่ยังยืนยันไม่ได้"


def build_decision_context(state: dict[str, Any]) -> dict[str, Any]:
    """Compose one canonical decision object from already-derived evidence."""
    structural_bias = _structural_bias(state)
    tactical_direction = _tactical_direction(state, structural_bias)
    location = _location(state)
    options = {
        "gamma": _gamma_context(state),
        "volatility": _volatility_context(state),
        "oi": _oi_context(state),
    }
    long_conf = _route_confirmations(state, "LONG", structural_bias)
    short_conf = _route_confirmations(state, "SHORT", structural_bias)

    conflicts: list[str] = []
    if structural_bias == "MIXED":
        conflicts.append("H4/H1 ไม่สอดคล้องกัน")
    if tactical_direction in {"BULLISH_AGAINST_STRUCTURE", "BEARISH_AGAINST_STRUCTURE"}:
        conflicts.append("ทิศทางระยะสั้นสวนโครงสร้างหลัก")
    if options["oi"]["activity"] in {"TWO_SIDED_BUILD", "MIXED_ACTIVITY"}:
        conflicts.append("Options activity ยังบ่งชี้เพียงการเคลื่อนไหวของสถานะ ไม่ใช่ aggressor direction")
    if options["volatility"]["movement"] == "COMPRESSING":
        conflicts.append("ความผันผวนระยะสั้นกำลังลดลง")
    if options["volatility"]["movement"] == "EXPANDING":
        conflicts.append("ความผันผวนระยะสั้นกำลังเพิ่มขึ้น")
    if options["gamma"] == "POSITIVE_GAMMA_DAMPENING_CONTEXT":
        conflicts.append("Gamma เป็นบวก: ใช้เป็นบริบทการชะลอการแกว่ง ไม่ใช่ข้อสรุปว่าจะเกิดกรอบราคา")
    elif options["gamma"] == "NEGATIVE_GAMMA_AMPLIFICATION_CONTEXT":
        conflicts.append("Gamma เป็นลบ: ใช้เป็นบริบทว่าการเคลื่อนไหวอาจถูกขยาย ไม่ใช่ directional signal")

    fresh_high = _fresh_high_news(state)
    catalyst = "ACTIVE" if fresh_high else "QUIET_OR_UNKNOWN"

    confirmed_sides = [
        side for side, data in (("BULLISH", long_conf), ("BEARISH", short_conf))
        if data.get("confirmed")
    ]
    if confirmed_sides:
        decision_state = f"{confirmed_sides[0]}_CONFIRMED"
        confirmation_state = "CONFIRMED"
        analysis_status = "CONFIRMED"
    elif structural_bias == "MIXED":
        decision_state = "WAIT_TRANSITION"
        confirmation_state = "NOT_CONFIRMED"
        analysis_status = "DEVELOPING"
    elif long_conf.get("state") == "TRIGGERED_WAIT_CONFIRMATION" or short_conf.get("state") == "TRIGGERED_WAIT_CONFIRMATION":
        decision_state = "WAIT_FOR_PRICE_CONFIRMATION"
        confirmation_state = "TRIGGERED_WAIT_CONFIRMATION"
        analysis_status = "DEVELOPING"
    else:
        decision_state = f"WAIT_{structural_bias}"
        confirmation_state = "NOT_CONFIRMED"
        analysis_status = "DEVELOPING"

    # A level trigger is intentionally separate from confirmation. It tells
    # legacy consumers that price has crossed the relevant structural level;
    # the decision_state remains WAIT until price-structure confirmation passes.
    price_current = _n((state.get("price") or {}).get("cfd"))
    levels = state.get("levels") or {}
    structural_resistance = _n(levels.get("resistance_current"))
    structural_support = _n(levels.get("support_current"))
    level_trigger = "NO_TRIGGER"
    if structural_bias == "BEARISH" and price_current is not None and structural_resistance is not None and price_current < structural_resistance:
        level_trigger = "SHORT_LEVEL_REACHED"
    elif structural_bias == "BULLISH" and price_current is not None and structural_support is not None and price_current > structural_support:
        level_trigger = "LONG_LEVEL_REACHED"

    legacy_decision = (
        "WAIT_MIXED_STRUCTURE"
        if structural_bias == "MIXED"
        else "SHORT_CONDITIONAL"
        if structural_bias == "BEARISH" and level_trigger == "SHORT_LEVEL_REACHED"
        else "LONG_CONDITIONAL"
        if structural_bias == "BULLISH" and level_trigger == "LONG_LEVEL_REACHED"
        else "WAIT_FOR_TRIGGER"
    )

    # Options never override the decision. They enrich the explanation layer.
    summary = (
        f"Structural bias={structural_bias}; tactical={tactical_direction}; "
        f"confirmation={confirmation_state}; options={options['gamma']}"
    )

    return {
        "version": "decision-engine-v1",
        "analysis_status": analysis_status,
        "structural_bias": structural_bias,
        "tactical_direction": tactical_direction,
        "location": location,
        "options_context": options,
        "confirmation_state": confirmation_state,
        "confirmation": {
            "LONG": long_conf,
            "SHORT": short_conf,
        },
        "decision_state": decision_state,
        "catalyst": catalyst,
        "conflicts": conflicts,
        "what_would_confirm": _what_would_confirm(structural_bias, state),
        "summary": summary,
        "rules": [
            "REGIME/structure precedes options context.",
            "Options explain pressure/mechanism; they do not override price confirmation.",
            "A level crossing is not confirmation.",
            "Missing or conflicting evidence resolves to WAIT/DEVELOPING.",
            "No IV high/low label without a baseline or percentile.",
        ],
        "legacy_framework": {
            "steps": {
                "1_market_state": {
                    "htf_structure": structural_bias.lower(),
                    "bullish_timeframes": [
                        tf for tf in ("h4", "h1", "m15", "m5", "m1")
                        if _trend(state, tf) == "bullish"
                    ],
                    "bearish_timeframes": [
                        tf for tf in ("h4", "h1", "m15", "m5", "m1")
                        if _trend(state, tf) == "bearish"
                    ],
                },
                "2_positioning": {
                    "source_oi_change": {
                        "put": _n((state.get("flow") or {}).get("oi_change_put")),
                        "call": _n((state.get("flow") or {}).get("oi_change_call")),
                        "total": _n((state.get("flow") or {}).get("oi_change_total")),
                        "put_state": (
                            "UP" if _n((state.get("flow") or {}).get("oi_change_put")) is not None and _n((state.get("flow") or {}).get("oi_change_put")) > 0
                            else "DOWN" if _n((state.get("flow") or {}).get("oi_change_put")) is not None and _n((state.get("flow") or {}).get("oi_change_put")) < 0
                            else "UNKNOWN"
                        ),
                        "call_state": (
                            "UP" if _n((state.get("flow") or {}).get("oi_change_call")) is not None and _n((state.get("flow") or {}).get("oi_change_call")) > 0
                            else "DOWN" if _n((state.get("flow") or {}).get("oi_change_call")) is not None and _n((state.get("flow") or {}).get("oi_change_call")) < 0
                            else "UNKNOWN"
                        ),
                    },
                    "vs_eod": {
                        "put": _n((state.get("flow") or {}).get("delta_oi_put")),
                        "call": _n((state.get("flow") or {}).get("delta_oi_call")),
                        "total": _n((state.get("flow") or {}).get("delta_oi_total")),
                    },
                    "churn": _n((state.get("flow") or {}).get("source_churn_total")),
                    "interpretation": options["oi"]["activity"],
                    "warning": "OI change/churn describe positioning activity; they do not identify aggressor direction.",
                },
                "3_gamma": {"regime": options["gamma"], "net_gex": _n((state.get("gamma") or {}).get("net_gex")), "dte": _n((state.get("price") or {}).get("dte"))},
                "4_history": state.get("history") or {},
                "5_catalyst": {"status": catalyst, "fresh_count": len(fresh_high)},
                "6_location": {"state": location},
                "7_gates": {
                    "htf_structure": structural_bias,
                    "positioning": options["oi"]["activity"],
                    "gamma": options["gamma"],
                    "catalyst": catalyst,
                    "trigger": level_trigger,
                },
                "8_decision": legacy_decision,
            },
            "rules": [
                "Directional context comes from H4/H1 structure.",
                "Options evidence cannot override price confirmation.",
                "A trigger is not confirmation.",
                "Conflict or missing evidence resolves to WAIT/DEVELOPING.",
            ],
        },
    }
