"""Customer-facing market narrative built from canonical evidence.

The engine translates technical evidence into plain Thai without creating new
prices, scores, or causal claims. It is presentation logic only: deterministic
inputs remain the source of truth and LLM text is treated as a verified
explanation layer.
"""
from __future__ import annotations

from typing import Any

from src.market_flow_engine import compact_market_flow


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

    decision = state.get("decision") or {}
    oi_activity = str(((decision.get("options_context") or {}).get("oi") or {}).get("activity") or "UNKNOWN").upper()
    if oi_activity == "TWO_SIDED_BUILD":
        parts.append("สถานะกำลังเพิ่มทั้งสองฝั่ง จึงยังไม่ใช่หลักฐานว่าผู้เล่นกำลังไล่ทางใด")
    elif oi_activity == "TWO_SIDED_REDUCTION":
        parts.append("สถานะทั้งสองฝั่งกำลังลดลง จึงยังไม่มี directional flow ที่ยืนยันได้")
    elif oi_activity == "MIXED_ACTIVITY":
        parts.append("การเปลี่ยนแปลงสถานะยังผสมกัน และไม่สามารถระบุ aggressor จากข้อมูลนี้ได้")
    else:
        parts.append("ข้อมูลสถานะยังไม่พอสำหรับระบุ directional flow")

    iv_change = _num(volatility.get("iv_change_1h"))
    if iv_change is not None and iv_change > 0:
        parts.append("ความผันผวนระยะสั้นกำลังขยาย แต่ยังไม่ใช่หลักฐานว่าราคาจะขึ้นหรือลง")
    elif iv_change is not None and iv_change < 0:
        parts.append("ความผันผวนระยะสั้นกำลังลดลง ทำให้แรงผลักจาก volatility อ่อนลง")

    h4 = _clean_text((technical.get("h4") or {}).get("trend")).lower()
    h1 = _clean_text((technical.get("h1") or {}).get("trend")).lower()
    if h4 and h1 and h4 != h1:
        parts.append("โครงสร้างกรอบเวลาหลักยังขัดกัน จึงควรรอให้ราคายืนยันทางใดทางหนึ่ง")

    decision = state.get("decision") or {}
    conflicts = decision.get("conflicts") or []
    if conflicts:
        parts.append("จุดที่ยังขัดกัน: " + "; ".join(str(x) for x in conflicts[:2]))
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
    decision = state.get("decision") or {}
    if str(decision.get("catalyst") or "").upper() == "ACTIVE":
        parts.append("มี catalyst สด จึงต้องรอ price response ก่อนเพิ่มน้ำหนักทิศทาง")
    return " ".join(part.strip() for part in parts if part and part.strip())


def _confirmation_read(parsed: dict[str, Any]) -> str:
    state = (parsed.get("raw_series") or {}).get("market_state") or {}
    decision = state.get("decision") or {}
    confirmation = str(decision.get("confirmation_state") or "NOT_CONFIRMED").upper()
    structural = str(decision.get("structural_bias") or "MIXED").upper()
    tactical = str(decision.get("tactical_direction") or "NEUTRAL").upper()
    decision_state = str(decision.get("decision_state") or "WAIT").upper()

    labels = {
        "CONFIRMED": "ยืนยันแล้ว",
        "TRIGGERED_WAIT_CONFIRMATION": "แตะ trigger แล้ว แต่ยังต้องยืนยัน",
        "NOT_CONFIRMED": "ยังไม่ยืนยัน",
        "DATA_INSUFFICIENT": "ข้อมูลไม่พอ",
    }
    headline = labels.get(confirmation, confirmation)

    what = decision.get("what_would_confirm") or {}
    bull = what.get("BULLISH") or []
    bear = what.get("BEARISH") or []
    next_lines = []
    if structural == "BULLISH":
        next_lines = bull[:2]
    elif structural == "BEARISH":
        next_lines = bear[:2]
    else:
        next_lines = bull[:1] + bear[:1]

    details = f"สถานะ {headline} | โครงสร้าง {structural} | ระยะสั้น {tactical} | {decision_state}"
    if next_lines:
        details += " | ยืนยันเมื่อ: " + " และ ".join(str(x) for x in next_lines)
    return details


def _decision_market_read(parsed: dict[str, Any], ai_result: dict[str, Any]) -> str:
    state = (parsed.get("raw_series") or {}).get("market_state") or {}
    decision = state.get("decision")
    if not isinstance(decision, dict):
        legacy = _clean_text(ai_result.get("market_overview") or ai_result.get("what"))
        return _friendly_text(legacy) or "ยังไม่มี market read ที่ยืนยันได้"

    structural = str(decision.get("structural_bias") or "MIXED").upper()
    tactical = str(decision.get("tactical_direction") or "NEUTRAL").upper()
    confirmation = str(decision.get("confirmation_state") or "NOT_CONFIRMED").upper()

    if confirmation == "CONFIRMED":
        side = "ขาขึ้น" if structural == "BULLISH" else "ขาลง" if structural == "BEARISH" else "ตาม setup ที่ยืนยัน"
        return f"โครงสร้างหลักและ price confirmation สอดคล้องกันแล้ว จึงมีทิศทาง{side}ที่ยืนยันจากข้อมูลราคา"
    if structural == "MIXED":
        return f"โครงสร้างหลักยังขัดกัน ขณะที่ระยะสั้นเป็น {tactical}; ตอนนี้ยังอยู่ในช่วงเปลี่ยนผ่านและยังไม่ยืนยันทาง"
    if tactical.endswith("_AGAINST_STRUCTURE"):
        side = "ขาลง" if structural == "BEARISH" else "ขาขึ้น"
        recovery = "กำลังฟื้นตัวระยะสั้น" if tactical.startswith("BULLISH") else "กำลังอ่อนตัวสวนแนวโน้มหลัก"
        return f"ภาพหลักยังเป็น{side} แต่ {recovery}; ยังไม่ใช่การกลับทิศที่ยืนยันแล้ว"
    side = "ขาขึ้น" if structural == "BULLISH" else "ขาลง"
    return f"โครงสร้างหลักยังเป็น{side} แต่ยังไม่มี price confirmation จึงรอ trigger/การยืนยันก่อน"



def _human_price_story(parsed: dict[str, Any], ai_result: dict[str, Any]) -> str:
    """Explain the market as a plain-Thai price story.

    Deterministic levels come only from the structural path. The wording may
    simplify mechanics, but it never invents a price or claims direct knowledge
    of dealer intent.
    """
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    path = ai_result.get("structural_path") or state.get("path") or {}
    current = _num(path.get("current_price")) or _num(parsed.get("cfd_price")) or _num(parsed.get("future_price"))
    if current is None:
        # Decision evidence is still useful even when a price/path snapshot is absent.
        # Keep the deterministic structural read instead of collapsing the message
        # into a generic data-missing sentence.
        decision_read = _decision_market_read(parsed, ai_result)
        if decision_read and decision_read != "ยังไม่มี market read ที่ยืนยันได้":
            return decision_read
        return "ตอนนี้ยังไม่มีราคาปัจจุบันที่ยืนยันได้ จึงยังวางเส้นทางราคาไม่ได้"

    upper = path.get("upper_node") or {}
    lower = path.get("lower_node") or {}
    next_up = path.get("next_up") or {}
    next_down = path.get("next_down") or {}
    up = _num(upper.get("level"))
    dn = _num(lower.get("level"))
    up2 = _num(next_up.get("level"))
    dn2 = _num(next_down.get("level"))

    def p(v: float | None) -> str:
        return _show(v, 2) if v is not None else "ยังไม่มีระดับถัดไปที่ยืนยันได้"

    def node_reason(node: dict[str, Any]) -> str:
        role = _clean_text(node.get("role")).upper()
        source = _clean_text(node.get("source")).lower()
        if role == "CALL_WALL":
            return "ด้านบนมีสถานะ Call กระจุกตัว ทำให้บริเวณนี้มีโอกาสเป็นด่านที่ราคาขึ้นแล้วชะลอ"
        if role == "PUT_WALL":
            return "ด้านล่างมีสถานะ Put กระจุกตัว ทำให้บริเวณนี้เป็นจุดที่ควรดูว่าราคาจะหยุดหรือเด้งหรือไม่"
        if role == "GAMMA_FLIP":
            return "บริเวณนี้เป็นจุดที่พฤติกรรมการป้องกันความเสี่ยงจาก Options อาจเปลี่ยน ทำให้ราคามีโอกาสเคลื่อนเร็วขึ้นเมื่อผ่าน"
        if "FVG" in role:
            return "บริเวณนี้เป็นพื้นที่ราคาที่เคยเคลื่อนผ่านเร็ว จึงอาจกลับมาทดสอบอีกครั้ง"
        if "SWING_HIGH" in role:
            return "บริเวณนี้เป็นจุดสูงเดิมที่ตลาดเคยขายกลับ"
        if "SWING_LOW" in role:
            return "บริเวณนี้เป็นจุดต่ำเดิมที่ตลาดเคยรับกลับ"
        if source == "options_strike":
            return "บริเวณนี้มีสถานะ Options กระจุกตัวในระดับราคานี้"
        return "บริเวณนี้เป็นระดับโครงสร้างที่ระบบพบจากข้อมูลราคาและตลาด Options"

    def recent_move() -> str:
        technical = parsed.get("technical_context") or {}
        ohlcv = technical.get("ohlcv") or {}
        bars = []
        if isinstance(ohlcv, dict):
            for value in ohlcv.values():
                if isinstance(value, list):
                    bars.extend(x for x in value if isinstance(x, dict))
        if not bars:
            return ""
        closes = []
        for bar in bars[-30:]:
            close = _num(bar.get("close"))
            if close is not None:
                closes.append(close)
        if len(closes) < 2:
            return ""
        start = closes[0]
        end = closes[-1]
        if end < start:
            return f"ช่วงข้อมูลล่าสุดราคาลดจากประมาณ {p(start)} มาที่ {p(end)}"
        if end > start:
            return f"ช่วงข้อมูลล่าสุดราคาขยับจากประมาณ {p(start)} มาที่ {p(end)}"
        return "ช่วงข้อมูลล่าสุดราคาแทบไม่เปลี่ยน"

    parts = ["ตอนนี้ทองอยู่ที่ประมาณ " + p(current) + " ครับ"]
    move = recent_move()
    if move:
        parts.append(move + " ทำให้ตอนนี้ราคากำลังเข้าใกล้จุดสำคัญด้านบนและด้านล่าง")

    if dn is not None and up is not None:
        parts.append(
            f"ด้านล่างมี {p(dn)} เป็นจุดรับ ส่วนด้านบนมี {p(up)} เป็นด่าน"
        )
        parts.append(
            f"ถ้าหลุด {p(dn)} ได้ ทางถัดไปคือ {p(dn2)}"
            + (f" และถ้า {p(dn2)} ยังรับไม่อยู่ ก็มีโอกาสลงต่อ" if dn2 is not None else "")
        )
        parts.append(
            f"แต่ถ้า {p(dn)} รับอยู่ ราคามีโอกาสเด้งกลับไปหา {p(up)}"
        )
        parts.append(
            f"ถ้าผ่าน {p(up)} ได้ ทางถัดไปคือ {p(up2)}"
            + (f" ส่วนถ้าขึ้นไปไม่ผ่าน {p(up)} ก็มีโอกาสกลับมาทดสอบ {p(dn)} อีกครั้ง" if up is not None else "")
        )
    elif dn is not None:
        parts.append(f"ตอนนี้จุดสำคัญอยู่ที่ {p(dn)} ด้านล่าง")
        parts.append(f"ถ้าหลุด {p(dn)} ได้ → {p(dn2)}")
        parts.append(f"ถ้าไม่หลุดและรับราคาอยู่ → มีโอกาสเด้งกลับขึ้น")
    elif up is not None:
        parts.append(f"ตอนนี้ด่านสำคัญอยู่ที่ {p(up)} ด้านบน")
        parts.append(f"ถ้าผ่าน {p(up)} ได้ → {p(up2)}")
        parts.append(f"ถ้าขึ้นไปไม่ผ่าน → มีโอกาสถอยกลับลงมาทดสอบฐานเดิม")
    else:
        parts.append("ตอนนี้ยังไม่มีระดับราคาที่มากพอจะสร้างเส้นทางขึ้นหรือลงอย่างน่าเชื่อถือ")

    if lower:
        parts.append("ทำไมจุดด้านล่างถึงสำคัญ? " + node_reason(lower))
    if upper:
        parts.append("ทำไมจุดด้านบนถึงสำคัญ? " + node_reason(upper))

    gamma = state.get("gamma") or {}
    net_gex = _num(gamma.get("net_gex"))
    if net_gex is not None:
        if net_gex < 0:
            parts.append("ตอนนี้โครงสร้างการป้องกันความเสี่ยงมีลักษณะที่ทำให้การเคลื่อนออกจากระดับสำคัญมีโอกาสแรงขึ้น")
        elif net_gex > 0:
            parts.append("ตอนนี้โครงสร้างการป้องกันความเสี่ยงมีลักษณะที่ช่วยให้ราคาชะลอและแกว่งรอบระดับสำคัญได้มากขึ้น")

    parts.append(
        "เราเห็นผลของการปรับการป้องกันความเสี่ยงจากโครงสร้าง Options "
        "แต่ไม่ได้หมายความว่าเรารู้ว่าผู้ดูแลสภาพคล่องตั้งใจจะดันหรือกดราคา"
    )
    return "\n\n".join(x for x in parts if x)


def build_customer_narrative(parsed: dict[str, Any], ai_result: dict[str, Any]) -> dict[str, str]:
    """Return the canonical human-readable market story plus supporting sections."""
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    volatility = state.get("volatility") or {}
    technical = state.get("technical") or {}

    # Deterministic decision state remains the source of truth.
    market_read = _human_price_story(parsed, ai_result)

    technical_llm = _friendly_text(ai_result.get("market_microstructure"))
    h4 = _clean_text((technical.get("h4") or {}).get("trend"))
    h1 = _clean_text((technical.get("h1") or {}).get("trend"))
    technical_text = technical_llm or "ยังไม่มีข้อมูล Technical ที่ยืนยันได้"
    if h4 and h1 and h4.lower() != h1.lower():
        technical_text += " แต่กรอบเวลาหลักยังให้ภาพต่างกัน"

    macro_text = _friendly_text(
        ai_result.get("macro") or "ยังไม่มีข้อมูลข่าวหรือปัจจัยภายนอกที่ยืนยันได้"
    )
    if not macro_text:
        macro_text = "ยังไม่มีข้อมูลข่าวหรือปัจจัยภายนอกที่ยืนยันได้"

    path = ai_result.get("structural_path") or state.get("path") or {}
    current = _num(path.get("current_price")) or _num(parsed.get("cfd_price"))
    market_flow = compact_market_flow(
        current, path, state
    ) if current is not None and isinstance(path, dict) else {
        "read": market_read, "flow": "ยังไม่มีเส้นทางราคาที่คำนวณได้"
    }

    return {
        "market_read": market_read,
        "volatility": _volatility_read(volatility, parsed),
        "oi_positioning": _oi_read(state.get("flow") or {}),
        "flow_statement": _flow_statement(parsed, ai_result),
        "why_now": _why_now(parsed, ai_result),
        "confirmation": _confirmation_read(parsed),
        "technical": technical_text,
        "macro_news": macro_text,
        "price_path": market_flow.get("flow") or "ยังไม่มีเส้นทางราคาที่คำนวณได้",
    }
