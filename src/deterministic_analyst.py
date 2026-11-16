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



def _smart_reference(parsed: dict[str, Any], history: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Choose the historical anchor that best explains a meaningful change."""
    now = _num(parsed.get("future_price"))
    candidates: list[tuple[str, dict[str, Any], float]] = []

    def add(label: str, row: dict[str, Any] | None) -> None:
        if not isinstance(row, dict):
            return
        price = _num(row.get("future_price"))
        if now is None or price is None:
            return
        delta = abs(now - price)
        raw = row.get("raw_series") or {}
        gex = raw.get("gex") or {}
        current_gex = _num(((parsed.get("raw_series") or {}).get("gex") or {}).get("net_gex"))
        base_gex = _num(gex.get("net_gex"))
        score = min(delta / max(now, 1.0) * 800.0, 4.0)
        if current_gex is not None and base_gex is not None and (current_gex < 0) != (base_gex < 0):
            score += 4.0
        candidates.append((label, row, score))

    add("ชั่วโมงก่อน", history.get("hour_ago"))
    add("ช่วงก่อนหน้า", history.get("two_hours_ago"))

    today = history.get("today") or {}
    if today.get("first_snapshot_time") and today.get("future_price_open") is not None:
        add("ช่วงเปิด session", {
            "captured_at": today.get("first_snapshot_time"),
            "future_price": today.get("future_price_open"),
            "vol": today.get("vol_first"),
            "raw_series": {"gex": today.get("oi_first") or {}},
        })

    yesterday = history.get("yesterday") or {}
    if yesterday.get("count") and yesterday.get("future_price_last") is not None:
        add("session ก่อน", {
            "captured_at": yesterday.get("latest_snapshot_time"),
            "future_price": yesterday.get("future_price_last"),
            "vol": yesterday.get("vol_last"),
            "raw_series": {"gex": yesterday.get("oi_last") or {}},
        })

    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[2], reverse=True)
    label, row, score = candidates[0]
    if score < 0.35:
        return None, None
    return label, row


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
    # H4 is the structural anchor; H1 is confirmation/transition context.
    # Do not collapse a clear H4 thesis into MIXED merely because H1 is moving.
    htf = (
        "BULLISH" if h4 == "bullish"
        else "BEARISH" if h4 == "bearish"
        else "BULLISH" if h1 == "bullish"
        else "BEARISH" if h1 == "bearish"
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
    quant = state.get("quant_metrics") or {}
    q_returns = quant.get("returns") or {}
    q_oi = quant.get("open_interest") or {}
    q_gamma = quant.get("gamma") or {}
    q_vol = quant.get("volatility") or {}
    q_risk = quant.get("risk_flags") or []
    fresh_news = [
        x for x in news
        if isinstance(x, dict)
        and str(x.get("freshness") or "").upper() in {"FRESH", "RECENT"}
    ]

    trigger = str((state.get("decision_framework") or {}).get("steps", {}).get("8_decision") or "")
    if not trigger:
        trigger = "WAIT_FOR_LIQUIDITY_TRIGGER" if htf != "MIXED" else "WAIT_FOR_STRUCTURE_RESOLUTION"

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

    # Build the same change-first story the live renderer expects, so an LLM
    # outage does not send the old indicator-by-indicator fallback article.
    hour = history.get("hour_ago") or {}
    yesterday = history.get("yesterday") or {}
    current_price = cfd if cfd is not None else future
    current_history_price = future if future is not None else cfd
    h1_price = _num(hour.get("future_price"))
    d1_price = _num(yesterday.get("future_price_last")) if yesterday.get("count") else None
    h1_delta = current_history_price - h1_price if current_history_price is not None and h1_price is not None else None
    d1_delta = current_history_price - d1_price if current_history_price is not None and d1_price is not None else None
    direction_text = "ขาขึ้น" if htf == "BULLISH" else "ขาลง" if htf == "BEARISH" else "ยังไม่ชัดเจน"
    overview = (
        f"ตอนนี้ทองอยู่แถว {_fmt(current_price)} และโครงสร้างหลักเป็น{direction_text}. "
        + ("ภาพหลักยังให้น้ำหนักฝั่งลงมากกว่าฝั่งขึ้น" if htf == "BEARISH" else "ภาพหลักยังให้น้ำหนักฝั่งขึ้นมากกว่าฝั่งลง" if htf == "BULLISH" else "ยังต้องรอการเปลี่ยนโครงสร้าง")
    )

    reference_label, reference_row = _smart_reference(parsed, history)
    comparison_bits = []
    reference_price = _num((reference_row or {}).get("future_price"))
    reference_delta = current_history_price - reference_price if current_history_price is not None and reference_price is not None else None
    if reference_label and reference_delta is not None:
        comparison_bits.append(
            f"เมื่อเทียบกับ{reference_label} ราคาปัจจุบัน"
            f"{'ลดลง' if reference_delta < 0 else 'เพิ่มขึ้น' if reference_delta > 0 else 'แทบไม่เปลี่ยน'} และ "
            + (f"ยังอยู่ต่ำกว่าโซนสำคัญ {_fmt(call_wall)}" if htf == "BEARISH" and call_wall is not None and current_price < call_wall else
               f"ยังอยู่เหนือโซนสำคัญ {_fmt(put_wall)}" if htf == "BULLISH" and put_wall is not None and current_price > put_wall else
               "ตำแหน่งเมื่อเทียบกับโซนสำคัญยังไม่เปลี่ยนชัดเจน")
        )
    else:
        history_story = "ตั้งแต่ช่วงก่อนหน้า โครงสร้างยังไม่เปลี่ยนอย่างมีนัยสำคัญจาก baseline ที่ระบบยืนยันได้"
    history_story = " ".join(comparison_bits) if comparison_bits else history_story

    why_parts = []
    if net_gex is not None:
        why_parts.append(gamma_context.replace("Positive gamma → context มีแนวโน้ม dampen/mean-revert", "Gamma เป็นบวก จึงมีแนวโน้มช่วยชะลอการแกว่ง")
                           .replace("Negative gamma → context มีโอกาส amplify movement", "Gamma เป็นลบ จึงมีโอกาสขยายการเคลื่อนไหวของราคา"))
    iv_change = _num((state.get("volatility") or {}).get("iv_change_1h"))
    skew_value = _num((state.get("volatility") or {}).get("skew"))
    if iv_change is not None and iv_change > 0:
        why_parts.append("ความผันผวนระยะสั้นยังขยายตัวเมื่อเทียบกับชั่วโมงก่อน")
    elif iv_change is not None and iv_change < 0:
        why_parts.append("ความผันผวนระยะสั้นเริ่มลดลงเมื่อเทียบกับชั่วโมงก่อน")
    if skew_value is not None and skew_value > 0:
        why_parts.append("Put Skew ยังเอียงไปทาง downside สะท้อนการจ่าย premium เพื่อป้องกันความเสี่ยงฝั่งลง")
    if put_change is not None and call_change is not None and put_change > 0 and call_change > 0:
        why_parts.append("OI เพิ่มทั้งสองฝั่ง จึงสะท้อนกิจกรรมของสถานะมากกว่าจะบอกว่าใครเป็น aggressor")
    why = " ".join(why_parts) or "หลักฐาน options/volatility ที่ใช้ขยายเหตุผลยังไม่ครบ"

    # Do not dump conflict labels into the customer article. Keep them as
    # internal evidence while the narrative states the actual implication.

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
            f"Net GEX {_fmt(net_gex,1)} | IV {_fmt(iv,2)}% | DTE {_fmt(dte,2)} | {gamma_context}; "
            f"IV-realized proxy={_fmt(q_vol.get('iv_minus_realized_proxy'),4)} | "
            f"GEX/total OI={_fmt(q_gamma.get('gex_per_total_oi'),2)}"
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
            f"Call/Put OI={_fmt(q_oi.get('call_put_ratio'),2)} | OI imbalance={_fmt(q_oi.get('imbalance'),3)} | "
            f"Churn {_fmt(churn,2)}"
        ),
        "history_comparison": history_story,
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
            "thesis หลักยังเป็นฝั่งขาลง; ไม่ควรไล่ Short และรอ Buy-side Liquidity Sweep ก่อนเข้า" 
            if htf == "BEARISH" else
            "thesis หลักยังเป็นฝั่งขาขึ้น; ไม่ควรไล่ Long และรอ Sell-side Liquidity Sweep ก่อนเข้า"
            if htf == "BULLISH" else
            "รอการเปลี่ยนโครงสร้างที่ชัดเจนก่อนเลือกฝั่ง"
        ),
        "data_limitations": [
            "LLM output unavailable or rejected: " + str(error)[:300],
            "Quant risk flags: " + (", ".join(q_risk) if q_risk else "NONE/UNKNOWN"),
            "Fallback does not infer dealer positioning from GEX.",
            "OI Change/Churn are activity evidence, not aggressor direction.",
        ],
        "evidence_refs": evidence_refs,
    }
