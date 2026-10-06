"""Deterministic analyst fallback.

Produces a useful conditional market read when the LLM path is unavailable.
This module never invents prices or directional positioning.
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def _fmt(v: Any, digits: int = 2) -> str:
    n = _num(v)
    return f"{n:,.{digits}f}" if n is not None else "UNKNOWN"


def _state(parsed: dict[str, Any]) -> dict[str, Any]:
    return (parsed.get("raw_series") or {}).get("market_state") or {}


def _technical(parsed: dict[str, Any]) -> dict[str, Any]:
    return parsed.get("technical_context") or {}


def build_deterministic_fallback(
    parsed: dict[str, Any],
    history: dict[str, Any] | None,
    *,
    error: str,
) -> dict[str, Any]:
    """Build a conditional analyst, not a data-dump fallback."""
    history = history or {}
    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    gex = raw.get("gex") or {}
    state = _state(parsed)
    flow = state.get("flow") or {}
    gamma = state.get("gamma") or {}
    technical = _technical(parsed)
    timeframes = technical.get("timeframes") or {}
    trends = {
        tf: str((ctx or {}).get("trend") or "").lower()
        for tf, ctx in timeframes.items()
        if isinstance(ctx, dict)
    }
    h4, h1 = trends.get("h4"), trends.get("h1")
    m15, m5 = trends.get("m15"), trends.get("m5")
    htf = (
        "BULLISH" if h4 == "bullish" and h1 == "bullish"
        else "BEARISH" if h4 == "bearish" and h1 == "bearish"
        else "MIXED"
    )

    future = _num(parsed.get("future_price"))
    cfd = _num(parsed.get("cfd_price"))
    basis = _num(parsed.get("basis_diff"))
    call_wall = _num(gamma.get("call_wall"))
    put_wall = _num(gamma.get("put_wall"))
    if call_wall is None:
        call_wall = _num(gex.get("call_wall"))
    if put_wall is None:
        put_wall = _num(gex.get("put_wall"))

    # market_state gamma walls are already in normalized CFD coordinates.
    current = cfd
    net_gex = _num(gamma.get("net_gex"))
    iv = _num(gamma.get("iv")) or _num(parsed.get("vol"))
    dte = _num(parsed.get("dte"))
    put_oi = _num(flow.get("oi_put"))
    call_oi = _num(flow.get("oi_call"))
    put_change = _num(flow.get("oi_change_put"))
    call_change = _num(flow.get("oi_change_call"))
    churn = _num(flow.get("source_churn_total"))
    news = parsed.get("news_context") or []
    fresh_news = [
        x for x in news
        if isinstance(x, dict)
        and str(x.get("freshness") or "").upper() in {"FRESH", "RECENT"}
    ]

    trigger = str((state.get("decision_framework") or {}).get("steps", {}).get("8_decision") or "")
    if not trigger:
        if htf == "MIXED":
            trigger = "WAIT_MIXED_STRUCTURE"
        else:
            trigger = "WAIT_FOR_TRIGGER"

    conflict = []
    if htf == "MIXED":
        conflict.append("H4/H1 ไม่สอดคล้องกัน")
    if put_change is not None and call_change is not None and put_change > 0 and call_change > 0:
        conflict.append("Put และ Call OI Change เพิ่มพร้อมกัน จึงยังไม่ใช่ directional signal")
    if basis is not None and abs(basis) > 10:
        conflict.append("Futures/CFD basis สูง ต้องระวังการเทียบ level ข้าม instrument")
    if fresh_news:
        conflict.append("มี catalyst สด ต้องรอ price response ก่อนให้น้ำหนักทิศทาง")

    # Never claim dealer direction from GEX alone.
    gamma_context = (
        "Positive gamma → context มีแนวโน้ม dampen/mean-revert"
        if net_gex is not None and net_gex > 0
        else "Negative gamma → context มีโอกาส amplify movement"
        if net_gex is not None and net_gex < 0
        else "Gamma regime UNKNOWN"
    )

    long_condition = (
        f"ต้องเห็น price acceptance/retest เหนือ Call Wall { _fmt(call_wall) } "
        "และ H1/M15 ยืนยัน bullish structure"
        if call_wall is not None
        else "ต้องมี bullish structure + breakout/acceptance ที่มีหลักฐาน"
    )
    short_condition = (
        f"ต้องเห็น break/retest-failure ใต้ Put Wall { _fmt(put_wall) } "
        "และ H1/M15 ยืนยัน bearish structure"
        if put_wall is not None
        else "ต้องมี bearish structure + downside break ที่มีหลักฐาน"
    )

    if htf == "BULLISH":
        bias = "LONG_CONDITIONAL"
    elif htf == "BEARISH":
        bias = "SHORT_CONDITIONAL"
    else:
        bias = "WAIT"

    status = "DEGRADED"
    overview = (
        f"โครงสร้าง {htf.lower()} แต่ยังเป็น conditional setup; "
        "fallback ใช้ deterministic evidence เท่านั้น"
    )
    if htf == "MIXED":
        overview = "H4/H1 ยัง mixed จึงยังไม่ให้ directional bias; รอ trigger ที่ตรวจสอบได้"

    why = (
        f"{gamma_context}; "
        f"OI activity = Put {_fmt(put_change,0)} / Call {_fmt(call_change,0)} "
        "บ่งชี้ activity สองฝั่ง ไม่ได้ระบุว่าใครเป็น aggressor"
    )
    if conflict:
        why += " | Conflict: " + "; ".join(conflict)

    evidence_refs = ["itb:oi:deterministic", "itb:oi:history"]
    if news:
        evidence_refs.append("itb:news:latest")

    return {
        "analysis_status": status,
        "market_overview": overview,
        "market_regime": "TRANSITION_UNCERTAIN" if htf == "MIXED" else htf,
        "macro": (
            f"มี {len(fresh_news)} fresh/recent news evidence; ใช้เป็น catalyst/risk factor "
            "และไม่ถือเป็น entry signal"
            if fresh_news else "ไม่มี fresh/recent macro catalyst ที่พร้อมยืนยัน direction"
        ),
        "financial_engineering": (
            f"Net GEX {_fmt(net_gex,1)} | IV {_fmt(iv,2)}% | DTE {_fmt(dte,2)} | {gamma_context}"
        ),
        "market_microstructure": (
            f"H4={h4 or 'UNKNOWN'} H1={h1 or 'UNKNOWN'} "
            f"M15={m15 or 'UNKNOWN'} M5={m5 or 'UNKNOWN'}; "
            "ต้องแยก level → break → acceptance/retest → trigger"
        ),
        "market_psychology": "ยังไม่ระบุ participant intent; OI/GEX เพียงอย่างเดียวไม่พอสำหรับ dealer/inventory claim",
        "what": (
            f"Futures {_fmt(future)} | CFD {_fmt(cfd)} | Basis {_fmt(basis)} | "
            f"Call Wall {_fmt(call_wall)} | Put Wall {_fmt(put_wall)}"
        ),
        "why": why,
        "positioning": (
            f"Current OI Put {_fmt(put_oi,0)} / Call {_fmt(call_oi,0)}; "
            f"OI Change Put {_fmt(put_change,0)} / Call {_fmt(call_change,0)}; "
            f"Churn {_fmt(churn,2)}"
        ),
        "history_comparison": (
            "ใช้ history เพื่อยืนยัน acceleration/deceleration เมื่อ metric มี baseline; "
            "ไม่มี baseline จะระบุ UNKNOWN เฉพาะ metric นั้น"
        ),
        "levels": {
            "resistance_main": call_wall,
            "support_main": put_wall,
            "resistance_current": call_wall,
            "support_current": put_wall,
        },
        "scenarios": {
            "bull": long_condition,
            "bear": short_condition,
            "sideway": "ถ้ายังไม่มี acceptance/break ที่ยืนยันได้ ให้ถือเป็น transition/range และรอ trigger",
        },
        "base_case": long_condition if htf == "BULLISH" else short_condition if htf == "BEARISH" else "WAIT_FOR_STRUCTURE_RESOLUTION",
        "alternative_case": short_condition if htf == "BULLISH" else long_condition if htf == "BEARISH" else "WAIT_FOR_STRUCTURE_RESOLUTION",
        "invalidation_case": "เมื่อ structure และ trigger ที่รองรับ thesis ไม่เป็นจริงหรือเกิด opposite acceptance/retest",
        "bias": bias,
        "uncertainty": 1.0 if htf == "MIXED" else 0.6,
        "why_not_long": [
            "ยังไม่มี confirmation ของ acceptance/retest สำหรับ long"
            if htf != "BULLISH" else "แม้ HTF bullish แต่ trigger ต้องยืนยันก่อน"
        ],
        "why_not_short": [
            "ยังไม่มี confirmation ของ break/retest-failure สำหรับ short"
            if htf != "BEARISH" else "แม้ HTF bearish แต่ trigger ต้องยืนยันก่อน"
        ],
        "trade_plan": {
            "status": "CONDITIONAL",
            "direction": bias,
            "long": {"condition": long_condition},
            "short": {"condition": short_condition},
            "market_condition": "DEGRADED / DETERMINISTIC FALLBACK",
            "risk_note": "Conditional roadmap only; not an execution instruction.",
        },
        "final_trade_idea": (
            f"Bias {bias}: ไม่ไล่ราคา; รอ {'bullish' if htf == 'BULLISH' else 'bearish' if htf == 'BEARISH' else 'structure'} confirmation "
            "แล้วค่อย activate scenario."
        ),
        "data_limitations": [
            "LLM output unavailable or rejected: " + str(error)[:300],
            "Fallback does not infer dealer positioning from GEX.",
            "OI Change/Churn are activity evidence, not aggressor direction.",
        ],
        "evidence_refs": evidence_refs,
    }
