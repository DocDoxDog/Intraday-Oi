"""Customer-facing market narrative built from canonical evidence.

The engine translates technical evidence into plain Thai without creating new
prices, scores, or causal claims. It is presentation logic only: deterministic
inputs remain the source of truth and LLM text is treated as a verified
explanation layer.
"""
from __future__ import annotations

from typing import Any

from src.market_flow_engine import compact_market_flow

# [run-live] final narrative wording
# [run-live] gamma-regime verification: state -> price response -> squeeze risk
# [run-live] regression: negative-gamma pocket must be explicit in customer story


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



def _gex_change_1h(parsed: dict[str, Any]) -> float | None:
    """Return the already-computed 1H Net GEX delta from canonical history.

    market_state.history["1h"]["gex"] is current-minus-previous. The old
    renderer subtracted it from current Net GEX a second time, which produced
    a misleading GEX change and made the customer story stale.
    """
    state = (parsed.get("raw_series") or {}).get("market_state") or {}
    return _num(((state.get("history") or {}).get("1h") or {}).get("gex"))


def _price_change_1h(parsed: dict[str, Any]) -> float | None:
    state = (parsed.get("raw_series") or {}).get("market_state") or {}
    return _num(((state.get("history") or {}).get("1h") or {}).get("price"))


def _nearest_negative_gamma(parsed: dict[str, Any], current: float | None) -> dict[str, Any] | None:
    if current is None:
        return None
    gamma = ((parsed.get("raw_series") or {}).get("market_state") or {}).get("gamma") or {}
    candidates = [
        x for x in (gamma.get("negative_concentrations") or [])
        if isinstance(x, dict) and _num(x.get("strike_cfd")) is not None
    ]
    if not candidates:
        zone = _num(gamma.get("negative_zone"))
        return {"strike_cfd": zone, "aggregate_gex": None} if zone is not None else None
    return min(candidates, key=lambda x: abs((_num(x.get("strike_cfd")) or 0.0) - current))


def _gamma_acceleration_read(
    parsed: dict[str, Any],
    current: float | None,
    *,
    direction: str,
) -> str:
    """Describe conditional gamma-squeeze risk without claiming dealer intent.

    Negative gamma is a volatility/hedging-feedback regime, not a directional
    signal by itself. Direction comes from the observed price path.
    """
    if current is None:
        return ""
    state = (parsed.get("raw_series") or {}).get("market_state") or {}
    gamma = state.get("gamma") or {}
    net_gex = _num(gamma.get("net_gex"))
    if net_gex is None or net_gex >= 0:
        return ""

    price_change = _price_change_1h(parsed)
    if price_change is None:
        technical = state.get("technical") or {}
        tf = "m5" if direction == "down" else "m5"
        trend = _clean_text((technical.get(tf) or {}).get("trend")).lower()
        price_change = -1.0 if trend in {"bearish", "bear", "down"} and direction == "down" else 1.0 if trend in {"bullish", "bull", "up"} and direction == "up" else None

    if price_change is None or (direction == "down" and price_change >= 0) or (direction == "up" and price_change <= 0):
        return ""

    zone = _nearest_negative_gamma(parsed, current)
    if not zone or _num(zone.get("strike_cfd")) is None:
        return (
            "Gamma รวมเป็นลบและราคากำลังเคลื่อนในทิศเดียวกัน จึงต้องระวังแรงเร่งจาก "
            "hedging feedback หากหลุดระดับสำคัญแล้วรับกลับไม่ได้"
        )

    level = _num(zone.get("strike_cfd"))
    gex = _num(zone.get("aggregate_gex"))
    if direction == "down":
        if current <= level:
            detail = f"ราคากำลังอยู่ใต้ negative-gamma pocket แถว {_show(level)}"
        else:
            detail = f"ราคากำลังเข้าใกล้ negative-gamma pocket แถว {_show(level)}"
        suffix = (
            f" โดยโซนนี้มี Gamma รวมประมาณ {_show(gex / 1_000_000, 2)}M"
            if gex is not None else ""
        )
        return (
            f"Gamma รวมเป็นลบ: {detail}{suffix}; ถ้าหลุดแล้ว Acceptance ใต้โซนได้ "
            "มีโอกาสเกิด downside gamma squeeze หรือแรงเร่งจากการปรับ hedge ตามราคา"
        )
    if current >= level:
        detail = f"ราคากำลังอยู่เหนือ negative-gamma pocket แถว {_show(level)}"
    else:
        detail = f"ราคากำลังเข้าใกล้ negative-gamma pocket แถว {_show(level)}"
    suffix = (
        f" โดยโซนนี้มี Gamma รวมประมาณ {_show(gex / 1_000_000, 2)}M"
        if gex is not None else ""
    )
    return (
        f"Gamma รวมเป็นลบ: {detail}{suffix}; ถ้าทะลุและ Acceptance เหนือโซนได้ "
        "มีโอกาสเกิด upside gamma squeeze หรือแรงเร่งจากการปรับ hedge ตามราคา"
    )


def _human_price_story(parsed: dict[str, Any], ai_result: dict[str, Any]) -> str:
    """Build the preferred desk-note narrative from state, change and cause.

    The story is causal: current location -> structure -> what changed ->
    gamma/liquidity mechanism -> conditional path. It does not turn Gamma/OI
    into a direction by itself.
    """
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    decision = state.get("decision") or {}
    gamma = state.get("gamma") or {}
    levels = state.get("levels") or {}
    technical = state.get("technical") or {}
    liquidity = state.get("liquidity") or {}

    def trend(tf: str) -> str:
        return _clean_text((technical.get(tf) or {}).get("trend")).lower()

    current = _num(parsed.get("cfd_price")) or _num((state.get("price") or {}).get("cfd"))
    support = _num(gamma.get("put_wall")) or _num(levels.get("support_current"))
    resistance = _num(gamma.get("call_wall")) or _num(levels.get("resistance_current"))
    net_gex = _num(gamma.get("net_gex"))
    gex_change = _gex_change_1h(parsed)
    price_change = _price_change_1h(parsed)

    if current is None:
        return _decision_market_read(parsed, ai_result)

    h4, h1, m15, m5 = (trend(x) for x in ("h4", "h1", "m15", "m5"))
    tactical_bull = any(x in {"bullish", "bull", "up"} for x in (m15, m5))
    tactical_bear = any(x in {"bearish", "bear", "down"} for x in (m15, m5))

    inside = support is not None and resistance is not None and support < current < resistance
    above = resistance is not None and current >= resistance
    below = support is not None and current <= support

    next_up = _num(levels.get("gamma_wall_up_next"))
    next_down = _num(levels.get("gamma_wall_down_next"))
    if next_up is not None and resistance is not None and next_up <= resistance:
        next_up = None
    if next_down is not None and support is not None and next_down >= support:
        next_down = None

    if inside:
        gamma_text = (
            "Gamma รวมยังเป็นลบ"
            if net_gex is not None and net_gex < 0
            else "Gamma รวมยังเป็นบวก"
            if net_gex is not None and net_gex > 0
            else "Gamma รวมยังไม่ชัด"
        )
        first = f"ตอนนี้ราคาทองยังอยู่ในกรอบ {_show(support)}–{_show(resistance)} โดย {gamma_text}"
        if h1 == "bearish" and tactical_bull:
            first += f" H1 ยังอยู่ในโครงสร้างขาลงและยังยืนเหนือ {_show(support)} ได้ และราคากำลังฟื้นกลับขึ้นไปหา Liquidity ด้านบนแถว {_show(resistance)}"
        elif h1 == "bullish" and tactical_bear:
            first += f" ขณะที่ H1 ยังเป็นขาขึ้น แต่ระยะสั้นกำลังย่อลงมาทดสอบ {_show(support)}"
        elif tactical_bull:
            first += f" และราคากำลังเด้งกลับขึ้นไปทดสอบ {_show(resistance)}"
        elif tactical_bear:
            first += f" และราคากำลังอ่อนตัวกลับมาทดสอบ {_show(support)}"
        else:
            first += f" โดย {_show(resistance)} เป็นแนวต้านหลักและ {_show(support)} เป็นแนวรับหลัก"

        if gex_change is not None and abs(gex_change) >= 1e-9:
            direction = "ดีขึ้น" if gex_change > 0 else "แย่ลง"
            change = (
                f"สิ่งที่เปลี่ยนจากชั่วโมงก่อนคือ Gamma {direction} "
                f"{'+' if gex_change > 0 else ''}{gex_change / 1_000_000:.2f}M"
            )
            if h4 and h1 and h4 == h1:
                change += f" แต่โครงสร้าง {h4.upper()} ยังไม่เปลี่ยน ดังนั้นการเคลื่อนที่แถว {_show(current)} ยังให้น้ำหนักเป็นการเคลื่อนที่ภายในกรอบมากกว่าการกลับตัว"
            else:
                change += " จึงยังไม่ใช่หลักฐานเพียงพอที่จะเปลี่ยน thesis"
        else:
            change = "สิ่งที่เปลี่ยนจากชั่วโมงก่อนยังไม่มีหลักฐาน GEX ที่ยืนยันได้มากพอ จึงยังไม่ควรใช้การเปลี่ยนแปลงของ Gamma เพียงอย่างเดียวเปลี่ยน thesis"

        oi_put = _num((state.get("flow") or {}).get("oi_change_put"))
        oi_call = _num((state.get("flow") or {}).get("oi_change_call"))
        if oi_put is not None and oi_call is not None and oi_put > 0 and oi_call > 0:
            change += f" OI เพิ่มทั้ง Put และ Call ({_show(oi_put, 0)} / {_show(oi_call, 0)}) จึงยังไม่ใช่ directional signal โดยตัวมันเอง"

        third = (
            f"ตอนนี้จึงไม่ควรไล่ราคาในกลางกรอบ รอให้ราคาไปทดสอบขอบก่อน; "
            f"ถ้ายืนเหนือ {_show(resistance)} ได้ จะเป็น Break + Acceptance และเปิดทางไปหา"
        )
        third += f" Gamma Wall ถัดไป {_show(next_up)}" if next_up is not None else "ระดับด้านบนถัดไป"
        if str(decision.get("structural_bias") or "").upper() == "BEARISH":
            third += f" แต่ถ้ากวาดเหนือ {_show(resistance)} แล้วกลับเข้า Range ให้ระวัง Buy-side Sweep และการย่อลงหา {_show(support)}"
        elif str(decision.get("structural_bias") or "").upper() == "BULLISH":
            third += f" ขณะที่ถ้าหลุด {_show(support)} แล้วกลับเข้า Range ให้ระวัง Sell-side Sweep และการเด้งกลับหา {_show(resistance)}"

        acceleration = _gamma_acceleration_read(
            parsed, current, direction="up" if tactical_bull or price_change is not None and price_change > 0 else "down"
        )
        if acceleration and net_gex is not None and net_gex < 0:
            third += f" {acceleration}."
        return "\n".join([first, change, third])

    if above and resistance is not None:
        first = f"ราคาขึ้นเหนือ {_show(resistance)} แล้ว และตอนนี้กำลังทดสอบว่าจะยืนเหนือโซนนี้ได้หรือไม่"
        second = (
            f"ถ้ายืนเหนือ {_show(resistance)} ได้ จะเป็น Break + Acceptance"
            + (f" และมีโอกาสไปต่อหา Gamma Wall ถัดไป {_show(next_up)}" if next_up is not None else " และเปิดทางขึ้นต่อ")
        )
        acceleration = _gamma_acceleration_read(parsed, current, direction="up")
        if acceleration:
            second += f" {acceleration}"
        third = f"แต่ถ้ากลับเข้า Range ให้ระวัง Failed Break และการกลับมาทดสอบ {_show(resistance)} อีกครั้ง"
        return "\n".join([first, second, third])

    if below and support is not None:
        first = f"ราคาหลุด {_show(support)} ลงมาแล้ว และตอนนี้กำลังทดสอบว่าจะยืนต่ำกว่าโซนนี้ได้หรือไม่"
        second = (
            f"ถ้ายืนต่ำกว่า {_show(support)} ได้ จะเป็น Break + Acceptance"
            + (f" และมีโอกาสลงต่อหา Gamma Wall ถัดไป {_show(next_down)}" if next_down is not None else " และเปิดทางลงต่อ")
        )
        acceleration = _gamma_acceleration_read(parsed, current, direction="down")
        if acceleration:
            second += f" {acceleration}"
        third = f"แต่ถ้ากลับขึ้นเหนือ {_show(support)} ให้ระวัง Failed Break และการกลับเข้า Range"
        return "\n".join([first, second, third])

    gate = str(liquidity.get("gate") or "").upper()
    preferred = str(liquidity.get("preferred_event") or "").upper()
    event = "Buy-side Sweep" if preferred == "BUY_SIDE_SWEEP" else "Sell-side Sweep" if preferred == "SELL_SIDE_SWEEP" else ""
    fallback = _decision_market_read(parsed, ai_result)
    why = _friendly_text(ai_result.get("why") or "")
    if why and why not in fallback:
        fallback = f"{fallback}\n{why}"
    if gate == "SWEEP_DETECTED" and event:
        return fallback + f"\nเกิด {event} แล้ว"
    return fallback

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
