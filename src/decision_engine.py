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
        return tactical.upper() if tactical != "neutral" else "NEUTRAL"
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


def _location(state: dict[str, Any]) -> str:
    price = state.get("price") or {}
    current = _n(price.get("cfd"))
    levels = state.get("levels") or {}
    resistance = _n(levels.get("resistance_current"))
    support = _n(levels.get("support_current"))
    if current is None or resistance is None or support is None:
        return "UNKNOWN"
    if current >= resistance:
        return "ABOVE_RESISTANCE"
    if current <= support:
        return "BELOW_SUPPORT"
    return "INSIDE_STRUCTURE"


def _side_confirmation(
    state: dict[str, Any],
    side: str,
    *,
    structural_bias: str,
    location: str,
) -> dict[str, Any]:
    technical = state.get("technical") or {}
    m15 = _trend(state, "m15")
    m5 = _trend(state, "m5")
    bos = _bos(state, "m5")
    price = state.get("price") or {}
    current = _n(price.get("cfd"))
    levels = state.get("levels") or {}
    trigger = _n(
        levels.get("resistance_current")
        if side == "LONG"
        else levels.get("support_current")
    )

    if current is None or trigger is None:
        return {
            "state": "DATA_INSUFFICIENT",
            "confirmed": False,
            "conditions": ["price_and_trigger_required"],
            "trigger": trigger,
        }

    if side == "LONG":
        location_ok = current > trigger
        structure_ok = structural_bias == "BULLISH" and m15 == "bullish" and m5 == "bullish"
        bos_ok = bos in LONG_BOS
        condition_names = [
            "htf_bullish" if structural_bias == "BULLISH" else "htf_not_bullish",
            "m15_bullish" if m15 == "bullish" else "m15_not_bullish",
            "m5_bullish" if m5 == "bullish" else "m5_not_bullish",
            "price_above_resistance" if location_ok else "waiting_break_above_resistance",
            "m5_bos_up" if bos_ok else "m5_bos_not_confirmed",
        ]
    else:
        location_ok = current < trigger
        structure_ok = structural_bias == "BEARISH" and m15 == "bearish" and m5 == "bearish"
        bos_ok = bos in SHORT_BOS
        condition_names = [
            "htf_bearish" if structural_bias == "BEARISH" else "htf_not_bearish",
            "m15_bearish" if m15 == "bearish" else "m15_not_bearish",
            "m5_bearish" if m5 == "bearish" else "m5_not_bearish",
            "price_below_support" if location_ok else "waiting_break_below_support",
            "m5_bos_down" if bos_ok else "m5_bos_not_confirmed",
        ]

    catalyst_active = bool(_fresh_high_news(state))
    regime = str((state.get("regime") or {}).get("regime") or "").upper()
    if catalyst_active or regime == "EVENT":
        event_gate = False
        condition_names.append("event_gate_active")
    else:
        event_gate = True

    if location_ok and structure_ok and bos_ok and event_gate:
        result = "CONFIRMED"
    elif location_ok:
        result = "TRIGGERED_WAIT_CONFIRMATION"
    elif current is not None:
        result = "ARMED"

    return {
        "state": result,
        "confirmed": result == "CONFIRMED",
        "trigger": trigger,
        "conditions": condition_names,
        "structure_aligned": structure_ok,
        "price_event": location_ok,
        "bos_confirmed": bos_ok,
        "event_gate": event_gate,
    }


def _what_would_confirm(structural_bias: str, state: dict[str, Any]) -> dict[str, list[str]]:
    levels = state.get("levels") or {}
    resistance = _n(levels.get("resistance_current"))
    support = _n(levels.get("support_current"))

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
    long_conf = _side_confirmation(
        state, "LONG", structural_bias=structural_bias, location=location
    )
    short_conf = _side_confirmation(
        state, "SHORT", structural_bias=structural_bias, location=location
    )

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
        if data["confirmed"]
    ]
    if confirmed_sides:
        decision_state = f"{confirmed_sides[0]}_CONFIRMED"
        confirmation_state = "CONFIRMED"
        analysis_status = "CONFIRMED"
    elif structural_bias == "MIXED":
        decision_state = "WAIT_TRANSITION"
        confirmation_state = "NOT_CONFIRMED"
        analysis_status = "DEVELOPING"
    elif long_conf["state"] == "TRIGGERED_WAIT_CONFIRMATION" or short_conf["state"] == "TRIGGERED_WAIT_CONFIRMATION":
        decision_state = "WAIT_FOR_PRICE_CONFIRMATION"
        confirmation_state = "TRIGGERED_WAIT_CONFIRMATION"
        analysis_status = "DEVELOPING"
    else:
        decision_state = f"WAIT_{structural_bias}"
        confirmation_state = "NOT_CONFIRMED"
        analysis_status = "DEVELOPING"

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
            "BEARISH": short_conf,
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
                "2_positioning": options["oi"],
                "3_gamma": {"regime": options["gamma"], "net_gex": _n((state.get("gamma") or {}).get("net_gex")), "dte": _n((state.get("price") or {}).get("dte"))},
                "4_history": state.get("history") or {},
                "5_catalyst": {"status": catalyst, "fresh_count": len(fresh_high)},
                "6_location": {"state": location},
                "7_gates": {
                    "htf_structure": structural_bias,
                    "positioning": options["oi"]["activity"],
                    "gamma": options["gamma"],
                    "catalyst": catalyst,
                    "trigger": (
                        "LONG_LEVEL_REACHED" if long_conf["price_event"]
                        else "SHORT_LEVEL_REACHED" if short_conf["price_event"]
                        else "NO_TRIGGER"
                    ),
                },
                "8_decision": decision_state,
            },
            "rules": [
                "Directional context comes from H4/H1 structure.",
                "Options evidence cannot override price confirmation.",
                "A trigger is not confirmation.",
                "Conflict or missing evidence resolves to WAIT/DEVELOPING.",
            ],
        },
    }
