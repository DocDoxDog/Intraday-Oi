"""Customer-facing market narrative built from canonical evidence.

The engine translates technical evidence into plain Thai without creating new
prices, scores, or causal claims. It is presentation logic only: deterministic
inputs remain the source of truth and LLM text is treated as a verified
explanation layer.
"""
from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _show(value: Any, digits: int = 2) -> str:
    n = _num(value)
    return f"{n:,.{digits}f}" if n is not None else "UNKNOWN"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _friendly_text(value: Any) -> str:
    """Translate common institutional jargon while preserving meaning."""
    text = _clean_text(value)
    if not text:
        return ""
    replacements = (
        ("Negative Gamma", "Gamma เป็นลบ"),
        ("Positive Gamma", "Gamma เป็นบวก"),
        ("negative gamma", "Gamma เป็นลบ"),
        ("positive gamma", "Gamma เป็นบวก"),
        ("OI activity", "กิจกรรมการเปิด/ปิดสถานะ"),
        ("OI Change", "การเปลี่ยนแปลงของสถานะคงค้าง"),
        ("aggressor", "ฝ่ายที่ไล่ซื้อหรือไล่ขาย"),
        ("Aggressor", "ฝ่ายที่ไล่ซื้อหรือไล่ขาย"),
        ("market maker", "ผู้ดูแลสภาพคล่อง"),
        ("Market Maker", "ผู้ดูแลสภาพคล่อง"),
        ("dealer", "ผู้ดูแลสภาพคล่อง"),
        ("Dealer", "ผู้ดูแลสภาพคล่อง"),
        ("acceptance/retest", "ยืนเหนือ/ใต้ระดับนั้นได้ แล้วกลับมาทดสอบซ้ำ"),
        ("acceptance / retest", "ยืนเหนือ/ใต้ระดับนั้นได้ แล้วกลับมาทดสอบซ้ำ"),
        ("break/retest-failure", "หลุดระดับ แล้วกลับมาทดสอบแต่ไม่ผ่าน"),
        ("retest-failure", "กลับมาทดสอบแล้วไม่ผ่าน"),
        ("conditional", "ยังต้องรอเงื่อนไขยืนยัน"),
        ("Conditional", "ยังต้องรอเงื่อนไขยืนยัน"),
        ("transition", "ช่วงเปลี่ยนผ่าน"),
        ("TRANSITION_UNCERTAIN", "ช่วงเปลี่ยนผ่าน • ทิศทางยังไม่ชัด"),
        ("TREND_UP", "แนวโน้มขึ้น"),
        ("TREND_DOWN", "แนวโน้มลง"),
        ("EVENT_DRIVEN", "ช่วงที่มีข่าว/เหตุการณ์สำคัญ"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _friendly_regime(value: Any) -> str:
    raw = _clean_text(value).upper()
    mapping = {
        "TREND": "แนวโน้มชัด",
        "TREND_UP": "แนวโน้มขึ้น",
        "TREND_DOWN": "แนวโน้มลง",
        "BALANCE": "ตลาดแกว่งในกรอบ",
        "TRANSITION": "ช่วงเปลี่ยนผ่าน",
        "TRANSITION_UNCERTAIN": "ช่วงเปลี่ยนผ่าน • ทิศทางยังไม่ชัด",
        "EVENT": "ช่วงรอข่าวสำคัญ",
        "EVENT_DRIVEN": "ช่วงที่มีข่าว/เหตุการณ์สำคัญ",
        "RANGE": "ตลาดแกว่งในกรอบ",
        "COMPRESSION": "การแกว่งแคบลง",
        "EXPANSION": "การแกว่งกว้างขึ้น",
        "REVERSAL": "อยู่ในช่วงกลับทิศ",
        "MIXED": "โครงสร้างขัดกัน",
        "UNKNOWN": "ไม่ทราบจากข้อมูล",
    }
    return mapping.get(raw, raw or "ไม่ทราบจากข้อมูล")


def _friendly_bias(value: Any) -> str:
    raw = _clean_text(value).upper()
    return {
        "BUY": "มองขึ้น",
        "SELL": "มองลง",
        "LONG": "มองขึ้น",
        "BEARISH": "มองลง",
        "BULLISH": "มองขึ้น",
        "WAIT": "รอดู",
        "LONG_CONDITIONAL": "รอเงื่อนไขฝั่งขึ้น",
        "SHORT_CONDITIONAL": "รอเงื่อนไขฝั่งลง",
    }.get(raw, raw or "รอดู")


def _oi_read(flow: dict[str, Any]) -> str:
    put_change = _num(flow.get("oi_change_put"))
    call_change = _num(flow.get("oi_change_call"))
    put_oi = _num(flow.get("oi_put"))
    call_oi = _num(flow.get("oi_call"))
    churn = _num(flow.get("source_churn_total"))

    if put_change is None and call_change is None:
        base = "ตอนนี้ยังไม่มีข้อมูลเปรียบเทียบ OI ที่เพียงพอสำหรับบอกว่าฝั่งไหนกำลังเพิ่มหรือลดสถานะ"
    elif put_change is not None and call_change is not None and put_change > 0 and call_change > 0:
        if abs(put_change - call_change) <= max(abs(put_change), abs(call_change)) * 0.15:
            base = (
                f"มีการเพิ่มสถานะทั้ง Put และ Call ใกล้เคียงกัน "
                f"(Put {_show(put_change, 0)} / Call {_show(call_change, 0)}) "
                "จึงยังสรุปไม่ได้ว่าตลาดเลือกทางขึ้นหรือทางลง"
            )
        elif put_change > call_change:
            base = (
                f"กิจกรรมฝั่ง Put มากกว่า Call "
                f"(Put {_show(put_change, 0)} / Call {_show(call_change, 0)}) "
                "แต่ OI อย่างเดียวบอกไม่ได้ว่าผู้เล่นกำลังซื้อหรือขายออปชัน"
            )
        else:
            base = (
                f"กิจกรรมฝั่ง Call มากกว่า Put "
                f"(Call {_show(call_change, 0)} / Put {_show(put_change, 0)}) "
                "แต่ OI อย่างเดียวบอกไม่ได้ว่าผู้เล่นกำลังซื้อหรือขายออปชัน"
            )
    elif put_change is not None and put_change > 0:
        base = f"กิจกรรมฝั่ง Put เพิ่มขึ้น {_show(put_change, 0)} แต่ยังใช้ OI เพียงอย่างเดียวฟันธงทิศทางไม่ได้"
    elif call_change is not None and call_change > 0:
        base = f"กิจกรรมฝั่ง Call เพิ่มขึ้น {_show(call_change, 0)} แต่ยังใช้ OI เพียงอย่างเดียวฟันธงทิศทางไม่ได้"
    elif put_change is not None and call_change is not None and put_change < 0 and call_change < 0:
        base = "สถานะทั้ง Put และ Call ลดลงพร้อมกัน สะท้อนว่ามีการลดสถานะออกจากตลาด"
    else:
        base = "การเปลี่ยนแปลงของ OI ยังไม่ชัดพอที่จะระบุทิศทาง"

    if churn is not None:
        base += f" | ปริมาณการหมุนสถานะ (Churn) {_show(churn, 2)}"
    if put_oi is not None and call_oi is not None:
        base += f" | OI ปัจจุบัน Put {_show(put_oi, 0)} / Call {_show(call_oi, 0)}"
    return base


def _volatility_read(volatility: dict[str, Any], parsed: dict[str, Any]) -> str:
    iv = _num(volatility.get("iv")) if volatility else _num(parsed.get("vol"))
    iv_change = _num(volatility.get("iv_change_1h")) if volatility else None
    dte = _num(parsed.get("dte"))
    parts = []
    if iv is not None:
        parts.append(f"IV อยู่ที่ {_show(iv, 2)}%")
    else:
        parts.append("ยังไม่มี IV ที่ยืนยันได้")
    if iv_change is not None:
        if iv_change > 0:
            parts.append("IV เพิ่มขึ้นเมื่อเทียบกับประมาณ 1 ชั่วโมงก่อน")
        elif iv_change < 0:
            parts.append("IV ลดลงเมื่อเทียบกับประมาณ 1 ชั่วโมงก่อน")
        else:
            parts.append("IV แทบไม่เปลี่ยนจากประมาณ 1 ชั่วโมงก่อน")
    if dte is not None:
        if dte <= 1:
            parts.append("สัญญาใกล้หมดอายุ จึงต้องระวังการเปลี่ยนแปลงที่เร็ว")
        else:
            parts.append(f"เหลืออายุสัญญาประมาณ {_show(dte, 2)} วัน")
    term = volatility.get("iv_term_structure") if isinstance(volatility, dict) else None
    valid_term = [
        x for x in (term or [])
        if isinstance(x, dict) and _num(x.get("dte")) is not None and _num(x.get("iv")) is not None
    ]
    if len(valid_term) >= 2:
        valid_term.sort(key=lambda x: _num(x.get("dte")) or 0.0)
        near_iv = _num(valid_term[0].get("iv"))
        far_iv = _num(valid_term[-1].get("iv"))
        if near_iv is not None and far_iv is not None:
            if near_iv > far_iv:
                parts.append("ความผันผวนในสัญญาใกล้หมดอายุถูกตั้งไว้สูงกว่าสัญญาที่ไกลกว่า")
            elif near_iv < far_iv:
                parts.append("ความผันผวนในสัญญาใกล้หมดอายุถูกตั้งไว้ต่ำกว่าสัญญาที่ไกลกว่า")
    skew = _num(volatility.get("skew")) if isinstance(volatility, dict) else None
    if skew is not None:
        if skew > 0:
            parts.append("IV ของ Put สูงกว่า Call ในจุดที่ระบบวัดได้")
        elif skew < 0:
            parts.append("IV ของ Call สูงกว่า Put ในจุดที่ระบบวัดได้")
        else:
            parts.append("IV ของ Put และ Call ใกล้เคียงกันในจุดที่ระบบวัดได้")
    return " | ".join(parts)


def _flow_statement(parsed: dict[str, Any], ai_result: dict[str, Any]) -> str:
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    flow = state.get("flow") or {}
    gamma = state.get("gamma") or {}
    volatility = state.get("volatility") or {}
    technical = state.get("technical") or {}
    current = _num(parsed.get("cfd_price"))
    put_wall = _num(gamma.get("put_wall"))
    call_wall = _num(gamma.get("call_wall"))
    net_gex = _num(gamma.get("net_gex"))
    parts = []

    if net_gex is not None and net_gex < 0:
        parts.append("Gamma เป็นลบ จึงมีโอกาสที่การเคลื่อนไหวจะถูกขยายเมื่อราคาออกจากระดับสำคัญ")
    elif net_gex is not None and net_gex > 0:
        parts.append("Gamma เป็นบวก จึงมีโอกาสช่วยลดความแรงของการแกว่งรอบระดับสำคัญ")
    else:
        parts.append("โครงสร้าง Gamma ยังไม่ชัดจากข้อมูลที่มี")

    if current is not None and put_wall is not None and call_wall is not None:
        if current <= put_wall:
            parts.append(f"ราคาอยู่ที่หรือต่ำกว่า Put Wall {_show(put_wall)} ซึ่งเป็นระดับที่ควรจับตา")
        elif current >= call_wall:
            parts.append(f"ราคาอยู่ที่หรือสูงกว่า Call Wall {_show(call_wall)} ซึ่งเป็นระดับที่ควรจับตา")
        else:
            parts.append(
                f"ราคาอยู่ระหว่าง Put Wall {_show(put_wall)} และ Call Wall {_show(call_wall)} "
                "จึงยังอยู่ในพื้นที่ระหว่างแนวสำคัญ"
            )
    elif current is not None:
        parts.append(f"ราคาปัจจุบันอยู่ที่ {_show(current)} แต่ยังมีระดับโครงสร้างไม่ครบ")

    parts.append(_oi_read(flow))

    iv_change = _num(volatility.get("iv_change_1h"))
    if iv_change is not None and iv_change > 0:
        parts.append("IV ที่เพิ่มขึ้นบอกว่าตลาดกำลังเผื่อการแกว่งมากขึ้น แต่ยังไม่ใช่หลักฐานว่าราคาจะขึ้นหรือลง")
    elif iv_change is not None and iv_change < 0:
        parts.append("IV ที่ลดลงบอกว่าความกังวลเรื่องการแกว่งลดลงเมื่อเทียบกับช่วงก่อนหน้า")

    h4 = _clean_text((technical.get("h4") or {}).get("trend")).lower()
    h1 = _clean_text((technical.get("h1") or {}).get("trend")).lower()
    if h4 and h1 and h4 != h1:
        parts.append("โครงสร้างกรอบเวลาหลักยังขัดกัน จึงควรรอให้ราคายืนยันทางใดทางหนึ่ง")

    if parts:
        # Keep the deterministic mechanism as the first sentence and let the
        # verified LLM explanation add nuance without becoming the sole source.
        llm = _friendly_text(ai_result.get("why"))
        if llm and llm not in parts:
            parts.append(llm)
    return " ".join(part.strip() for part in parts if part and part.strip())


def _why_now(parsed: dict[str, Any], ai_result: dict[str, Any]) -> str:
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    gamma = state.get("gamma") or {}
    volatility = state.get("volatility") or {}
    news = parsed.get("news_context") or []
    parts = []
    net_gex = _num(gamma.get("net_gex"))
    if net_gex is not None and net_gex < 0:
        parts.append("Gamma เป็นลบ ทำให้การหลุดระดับสำคัญมีโอกาสเร่งตัว")
    iv = _num(volatility.get("iv"))
    if iv is not None:
        parts.append(f"IV อยู่ที่ {_show(iv, 2)}%")
    if _num(volatility.get("iv_change_1h")) is not None and _num(volatility.get("iv_change_1h")) > 0:
        parts.append("IV กำลังเพิ่มขึ้นจากช่วงก่อนหน้า")
    fresh_high = [
        item for item in news
        if isinstance(item, dict)
        and str(item.get("freshness") or "").upper() in {"FRESH", "RECENT"}
        and str(item.get("relevance") or "").upper() in {"HIGH", "CRITICAL"}
    ]
    if fresh_high:
        headlines = [str(item.get("headline") or "").strip() for item in fresh_high[:2]]
        headlines = [x for x in headlines if x]
        if headlines:
            parts.append("มีข่าวสำคัญที่ยังใหม่อยู่: " + " / ".join(headlines))
    else:
        parts.append("ยังไม่มีข่าวใหม่ที่ระบบยืนยันว่าเกี่ยวข้องกับจังหวะนี้โดยตรง")
    llm = _friendly_text(ai_result.get("financial_engineering"))
    if llm and llm not in parts:
        parts.append(llm)
    return " ".join(part.strip() for part in parts if part and part.strip())


def build_customer_narrative(parsed: dict[str, Any], ai_result: dict[str, Any]) -> dict[str, str]:
    """Return concise customer-facing sections in plain Thai."""
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    volatility = state.get("volatility") or {}
    technical = state.get("technical") or {}

    market_read = _friendly_text(
        ai_result.get("market_overview")
        or ai_result.get("what")
        or "ยังไม่มี market read ที่ยืนยันได้"
    )
    if not market_read:
        market_read = "ยังไม่มี market read ที่ยืนยันได้"

    technical_llm = _friendly_text(ai_result.get("market_microstructure"))
    h4 = _clean_text((technical.get("h4") or {}).get("trend"))
    h1 = _clean_text((technical.get("h1") or {}).get("trend"))
    technical_text = technical_llm or "ยังไม่มีข้อมูล Technical ที่ยืนยันได้"
    if h4 and h1 and h4.lower() != h1.lower():
        technical_text += " ขณะนี้กรอบเวลาหลักยังให้ภาพต่างกัน"

    macro_text = _friendly_text(
        ai_result.get("macro") or "ยังไม่มีข้อมูล Macro/News ที่เพียงพอ"
    )
    if not macro_text:
        macro_text = "ยังไม่มีข้อมูล Macro/News ที่เพียงพอ"

    return {
        "market_read": market_read,
        "volatility": _volatility_read(volatility, parsed),
        "oi_positioning": _oi_read(state.get("flow") or {}),
        "flow_statement": _flow_statement(parsed, ai_result),
        "why_now": _why_now(parsed, ai_result),
        "technical": technical_text,
        "macro_news": macro_text,
    }
