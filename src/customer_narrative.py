"""Customer-facing market narrative compiler.

This module is a presentation boundary, not an analysis engine.
It selects a small number of already-derived facts and relationships and
turns them into one coherent Thai market story.

Rules:
- Never invent prices, causes, probabilities or participant identities.
- Prefer relationships over metric lists.
- Keep the customer summary chronological: now -> why -> what next -> invalidation.
- Keep trade-plan/execution semantics separate from the market story.
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


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _show(value: Any, digits: int = 2) -> str:
    number = _num(value)
    return f"{number:,.{digits}f}" if number is not None else ""


def _join_nonempty(parts: list[str], sep: str = " ") -> str:
    return sep.join(part.strip() for part in parts if part and part.strip())


def _friendly_text(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    replacements = (
        ("Negative Gamma", "Gamma เป็นลบ"),
        ("Positive Gamma", "Gamma เป็นบวก"),
        ("negative gamma", "Gamma เป็นลบ"),
        ("positive gamma", "Gamma เป็นบวก"),
        ("OI activity", "กิจกรรมของสถานะ"),
        ("OI Change", "การเปลี่ยนแปลงของสถานะคงค้าง"),
        ("aggressor", "ฝ่ายที่ไล่ซื้อหรือไล่ขาย"),
        ("Aggressor", "ฝ่ายที่ไล่ซื้อหรือไล่ขาย"),
        ("market maker", "ผู้ดูแลสภาพคล่อง"),
        ("Market Maker", "ผู้ดูแลสภาพคล่อง"),
        ("dealer", "ผู้ดูแลสภาพคล่อง"),
        ("Dealer", "ผู้ดูแลสภาพคล่อง"),
        ("acceptance/retest", "ยืนเหนือ/ใต้ระดับนั้นได้แล้วทดสอบซ้ำ"),
        ("acceptance / retest", "ยืนเหนือ/ใต้ระดับนั้นได้แล้วทดสอบซ้ำ"),
        ("break/retest-failure", "หลุดระดับแล้วกลับมาทดสอบแต่ไม่ผ่าน"),
        ("retest-failure", "กลับมาทดสอบแล้วไม่ผ่าน"),
        ("conditional", "ยังต้องรอเงื่อนไขยืนยัน"),
        ("Conditional", "ยังต้องรอเงื่อนไขยืนยัน"),
        ("TRANSITION_UNCERTAIN", "ช่วงเปลี่ยนผ่าน"),
        ("TREND_UP", "แนวโน้มขึ้น"),
        ("TREND_DOWN", "แนวโน้มลง"),
        ("EVENT_DRIVEN", "ช่วงที่มีข่าวหรือเหตุการณ์สำคัญ"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _friendly_regime(value: Any) -> str:
    raw = _clean(value).upper()
    return {
        "TREND": "แนวโน้มชัด",
        "TREND_UP": "แนวโน้มขึ้น",
        "TREND_DOWN": "แนวโน้มลง",
        "BULLISH": "แนวโน้มขึ้น",
        "BEARISH": "แนวโน้มลง",
        "BALANCE": "ตลาดแกว่งในกรอบ",
        "RANGE": "ตลาดแกว่งในกรอบ",
        "TRANSITION": "ช่วงเปลี่ยนผ่าน",
        "TRANSITION_UNCERTAIN": "ช่วงเปลี่ยนผ่าน",
        "EVENT": "ช่วงรอข่าวสำคัญ",
        "EVENT_DRIVEN": "ช่วงที่มีข่าวหรือเหตุการณ์สำคัญ",
        "COMPRESSION": "การแกว่งแคบลง",
        "EXPANSION": "การแกว่งกว้างขึ้น",
        "REVERSAL": "อยู่ในช่วงกลับทิศ",
        "MIXED": "โครงสร้างขัดกัน",
        "UNKNOWN": "ยังระบุไม่ได้",
    }.get(raw, raw or "ยังระบุไม่ได้")


def _friendly_bias(value: Any) -> str:
    raw = _clean(value).upper()
    return {
        "BUY": "มองขึ้น",
        "SELL": "มองลง",
        "LONG": "มองขึ้น",
        "SHORT": "มองลง",
        "BEARISH": "มองลง",
        "BULLISH": "มองขึ้น",
        "WAIT": "รอดู",
        "LONG_CONDITIONAL": "รอเงื่อนไขฝั่งขึ้น",
        "SHORT_CONDITIONAL": "รอเงื่อนไขฝั่งลง",
    }.get(raw, raw or "รอดู")


def _state(parsed: dict[str, Any]) -> dict[str, Any]:
    return (parsed.get("raw_series") or {}).get("market_state") or {}


def _decision(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("decision")
    return value if isinstance(value, dict) else {}


def _path(parsed: dict[str, Any], ai_result: dict[str, Any]) -> dict[str, Any]:
    raw = parsed.get("raw_series") or {}
    flow = raw.get("market_flow") or {}
    state = raw.get("market_state") or {}
    value = ai_result.get("structural_path") or flow.get("path") or state.get("path") or {}
    return value if isinstance(value, dict) else {}


def _node(path: dict[str, Any], key: str) -> dict[str, Any]:
    value = path.get(key) or {}
    return value if isinstance(value, dict) else {}


def _current(parsed: dict[str, Any], path: dict[str, Any]) -> float | None:
    return _num(path.get("current_price")) or _num(parsed.get("cfd_price")) or _num(parsed.get("future_price"))


def _state_sentence(state: dict[str, Any], parsed: dict[str, Any], path: dict[str, Any]) -> str:
    decision = _decision(state)
    structural = str(decision.get("structural_bias") or "").upper()
    tactical = str(decision.get("tactical_direction") or "").upper()
    confirmation = str(decision.get("confirmation_state") or "").upper()
    regime = _friendly_regime(
        (state.get("regime") or {}).get("regime")
        or decision.get("structural_bias")
        or "UNKNOWN"
    )

    direction = (
        "ขาขึ้น" if structural == "BULLISH"
        else "ขาลง" if structural == "BEARISH"
        else "ยังไม่ชัด"
    )

    if structural == "MIXED":
        lead = "ตอนนี้ตลาดอยู่ในช่วงเปลี่ยนผ่าน"
    elif confirmation == "CONFIRMED":
        lead = f"ตอนนี้โครงสร้างหลักเป็น{direction}และราคาเริ่มยืนยันทางเดียวกัน"
    elif tactical.endswith("_AGAINST_STRUCTURE"):
        lead = f"ภาพหลักยังเป็น{direction} แต่ระยะสั้นกำลังแกว่งสวน"
    else:
        lead = f"ตอนนี้ภาพหลักยังเป็น{direction} แต่ยังไม่ยืนยันการไปต่อ"

    current = _current(parsed, path)
    upper = _node(path, "upper_node").get("level")
    lower = _node(path, "lower_node").get("level")
    if current is None:
        return f"{lead} ({regime})"

    if _num(lower) is not None and _num(upper) is not None:
        location = f"ราคา { _show(current) } ยังอยู่ระหว่าง { _show(lower) } กับ { _show(upper) }"
    elif _num(upper) is not None:
        location = f"ราคาอยู่ใต้ { _show(upper) }"
    elif _num(lower) is not None:
        location = f"ราคาอยู่เหนือ { _show(lower) }"
    else:
        location = f"ราคาปัจจุบันอยู่ที่ {_show(current)}"

    return f"{lead}; {location}"


def _mechanism_sentence(state: dict[str, Any]) -> str:
    gamma = state.get("gamma") or {}
    volatility = state.get("volatility") or {}
    net_gex = _num(gamma.get("net_gex"))
    iv_change = _num(volatility.get("iv_change_1h"))
    dte = _num((state.get("price") or {}).get("dte"))

    parts: list[str] = []

    if net_gex is not None:
        if net_gex < 0:
            parts.append("Gamma เป็นลบ จึงต้องระวังว่าการออกจากระดับสำคัญอาจเร่งตัว")
        elif net_gex > 0:
            parts.append("Gamma เป็นบวก จึงมีบริบทว่าการแกว่งใกล้ระดับสำคัญอาจถูกหน่วง")
    if iv_change is not None:
        if iv_change > 0:
            parts.append("และความผันผวนระยะสั้นกำลังเพิ่มขึ้น")
        elif iv_change < 0:
            parts.append("และความผันผวนระยะสั้นกำลังลดลง")
    if dte is not None and dte <= 1:
        parts.append("สัญญาใกล้หมดอายุจึงต้องเผื่อว่าระดับจะเปลี่ยนเร็ว")

    if not parts:
        return "ตอนนี้ยังไม่มีหลักฐานพอที่จะบอกกลไกที่กำลังผลักราคา"
    return _join_nonempty(parts) + "."


def _oi_sentence(state: dict[str, Any]) -> str:
    flow = state.get("flow") or {}
    put_change = _num(flow.get("oi_change_put"))
    call_change = _num(flow.get("oi_change_call"))
    churn = _num(flow.get("source_churn_total"))

    if put_change is None and call_change is None:
        return "ฝั่งสถานะยังมีข้อมูลไม่พอที่จะบอกว่ากำลังเพิ่มหรือลดน้ำหนักไปทางใด"

    if (
        put_change is not None and call_change is not None
        and put_change > 0 and call_change > 0
    ):
        if abs(put_change - call_change) <= max(abs(put_change), abs(call_change)) * 0.15:
            sentence = (
                f"สถานะ Put และ Call เพิ่มขึ้นใกล้เคียงกัน "
                f"(Put {_show(put_change, 0)} / Call {_show(call_change, 0)}) "
                "จึงยังไม่ถือเป็นหลักฐานเลือกทาง"
            )
        elif put_change > call_change:
            sentence = (
                f"กิจกรรมฝั่ง Put มากกว่า Call "
                f"(Put {_show(put_change, 0)} / Call {_show(call_change, 0)}) "
                "แต่ OI ยังบอกไม่ได้ว่าเป็นฝ่ายซื้อหรือขาย"
            )
        else:
            sentence = (
                f"กิจกรรมฝั่ง Call มากกว่า Put "
                f"(Call {_show(call_change, 0)} / Put {_show(put_change, 0)}) "
                "แต่ OI ยังบอกไม่ได้ว่าเป็นฝ่ายซื้อหรือขาย"
            )
    elif put_change is not None and put_change > 0:
        sentence = f"สถานะฝั่ง Put เพิ่มขึ้น {_show(put_change, 0)} แต่ OI เพียงอย่างเดียวบอกไม่ได้ว่าใครเป็นฝ่ายซื้อหรือขาย"
    elif call_change is not None and call_change > 0:
        sentence = f"สถานะฝั่ง Call เพิ่มขึ้น {_show(call_change, 0)} แต่ OI เพียงอย่างเดียวบอกไม่ได้ว่าใครเป็นฝ่ายซื้อหรือขาย"
    elif put_change is not None and call_change is not None and put_change < 0 and call_change < 0:
        sentence = "สถานะทั้ง Put และ Call ลดลงพร้อมกัน จึงเห็นการลดสถานะมากกว่าการสร้าง directional position ใหม่"
    else:
        sentence = "การเปลี่ยนแปลงของสถานะยังผสมกัน จึงยังไม่ใช่หลักฐานของ directional flow"

    if churn is not None and churn != 0:
        sentence += f" Churn อยู่ที่ {_show(churn, 2)}"
    return sentence


def _history_sentence(state: dict[str, Any]) -> str:
    history = state.get("history") or {}
    one = history.get("1h") or {}
    price_change = _num(one.get("price"))
    iv_change = _num(one.get("vol"))
    gex_change = _num(one.get("gex"))

    parts: list[str] = []
    if price_change is not None:
        if price_change > 0:
            parts.append(f"จากประมาณ 1 ชั่วโมงก่อน ราคาเพิ่มขึ้น {_show(abs(price_change))}")
        elif price_change < 0:
            parts.append(f"จากประมาณ 1 ชั่วโมงก่อน ราคาลดลง {_show(abs(price_change))}")
        else:
            parts.append("จากประมาณ 1 ชั่วโมงก่อน ราคาแทบไม่เปลี่ยน")
    if iv_change is not None:
        if iv_change > 0:
            parts.append("ขณะที่ IV เพิ่มขึ้น")
        elif iv_change < 0:
            parts.append("ขณะที่ IV ลดลง")
    if gex_change is not None and gex_change != 0:
        parts.append("และโครงสร้าง Gamma เปลี่ยนจากช่วงก่อนหน้า")

    return _join_nonempty(parts) + "." if parts else ""


def _conflict_sentence(state: dict[str, Any], evidence: dict[str, Any]) -> str:
    decision = _decision(state)
    conflicts = decision.get("conflicts") or []
    if isinstance(conflicts, list):
        clean = [_friendly_text(x) for x in conflicts if _clean(x)]
        if clean:
            # Do not list every conflict. Human analysts name the one that
            # changes the decision most.
            return f"สิ่งที่ทำให้ภาพยังไม่ชัดคือ{clean[0]}"

    fusion_conflicts = evidence.get("conflicts") or []
    if fusion_conflicts:
        first = fusion_conflicts[0]
        if isinstance(first, dict):
            text = _friendly_text(first.get("interpretation") or first.get("resolution_hint"))
            if text:
                return f"สิ่งที่ต้องระวังคือ{text}"
    return ""


def _path_sentence(path: dict[str, Any]) -> str:
    upper = _node(path, "upper_node")
    lower = _node(path, "lower_node")
    next_up = _node(path, "next_up")
    next_down = _node(path, "next_down")

    parts: list[str] = []
    if _num(upper.get("level")) is not None:
        if _num(next_up.get("level")) is not None:
            parts.append(
                f"ถ้าราคาผ่าน {_show(upper.get('level'))} และยืนได้ จะเปิดทางไป {_show(next_up.get('level'))}"
            )
        else:
            parts.append(f"ถ้าราคาผ่าน {_show(upper.get('level'))} และยืนได้ ภาพจะเริ่มเปิดทางขึ้น")
        parts.append(
            f"แต่ถ้ายืนไม่ได้ ราคาอาจกลับเข้าโซนเดิม"
        )

    if _num(lower.get("level")) is not None:
        if _num(next_down.get("level")) is not None:
            parts.append(
                f"ฝั่งล่าง ถ้าหลุด {_show(lower.get('level'))} และยืนต่ำกว่า จะเปิดทางไป {_show(next_down.get('level'))}"
            )
        else:
            parts.append(f"ฝั่งล่าง ถ้าหลุด {_show(lower.get('level'))} และยืนต่ำกว่า ภาพจะเริ่มเปิดทางลง")

    return " ".join(parts)


def _invalidation_sentence(state: dict[str, Any], path: dict[str, Any]) -> str:
    decision = _decision(state)
    structural = str(decision.get("structural_bias") or "").upper()
    upper = _node(path, "upper_node").get("level")
    lower = _node(path, "lower_node").get("level")

    if structural == "BULLISH" and _num(lower) is not None:
        return f"มุมมองขึ้นจะอ่อนลงถ้าราคาหลุด {_show(lower)} แล้วกลับไปยืนไม่ได้"
    if structural == "BEARISH" and _num(upper) is not None:
        return f"มุมมองลงจะอ่อนลงถ้าราคากลับขึ้นเหนือ {_show(upper)} แล้วรับระดับนั้นได้"
    if structural == "MIXED":
        return "ตอนนี้สิ่งที่ทำให้ thesis เปลี่ยนคือการที่ราคายอมรับอยู่นอกกรอบด้านใดด้านหนึ่ง"
    return ""


def _fresh_news_sentence(parsed: dict[str, Any]) -> str:
    news = parsed.get("news_context") or []
    fresh = [
        item for item in news
        if isinstance(item, dict)
        and str(item.get("freshness") or "").upper() in {"FRESH", "RECENT"}
        and str(item.get("relevance") or "").upper() in {"HIGH", "CRITICAL"}
    ]
    if not fresh:
        return "ตอนนี้ยังไม่มีข่าวใหม่ที่ระบบยืนยันว่าเปลี่ยนเส้นทางของตลาดโดยตรง"

    headline = _clean(fresh[0].get("headline"))
    if headline:
        return f"มี catalyst ใหม่ที่ต้องเฝ้าดู: {headline}"
    return "มี catalyst ใหม่ที่ต้องรอดู price response ก่อนเพิ่มน้ำหนักทิศทาง"


def _technical_sentence(state: dict[str, Any]) -> str:
    technical = state.get("technical") or {}
    h4 = _clean((technical.get("h4") or {}).get("trend")).lower()
    h1 = _clean((technical.get("h1") or {}).get("trend")).lower()
    m15 = _clean((technical.get("m15") or {}).get("trend")).lower()
    m5 = _clean((technical.get("m5") or {}).get("trend")).lower()

    if h4 and h1 and h4 == h1:
        if m15 and m15 != h4:
            side = "ขึ้น" if h4 == "bullish" else "ลง"
            return f"กรอบใหญ่ยังเป็นฝั่ง{side} แต่ M15 กำลังสวน จึงยังไม่ควรตีความว่าเป็นการกลับทิศ"
        side = "ขึ้น" if h4 == "bullish" else "ลง"
        if m15 == h4 or m5 == h4:
            return f"กรอบ H4/H1 และระยะสั้นกำลังไปทาง{side}สอดคล้องกัน"
        return f"กรอบ H4/H1 ยังเป็นฝั่ง{side} แต่จังหวะสั้นยังไม่ชัด"

    if h4 and h1 and h4 != h1:
        return "H4 กับ H1 ยังให้ภาพต่างกัน จึงให้น้ำหนักกับการรอราคาแก้ความขัดแย้งก่อน"

    return ""


def _volatility_text(state: dict[str, Any], parsed: dict[str, Any]) -> str:
    volatility = state.get("volatility") or {}
    iv = _num(volatility.get("iv"))
    iv_change = _num(volatility.get("iv_change_1h"))
    dte = _num((state.get("price") or {}).get("dte"))
    parts: list[str] = []

    if iv is not None:
        parts.append(f"IV อยู่ที่ {_show(iv)}%")
    if iv_change is not None:
        parts.append(
            "IV กำลังเพิ่มขึ้น" if iv_change > 0
            else "IV กำลังลดลง" if iv_change < 0
            else "IV แทบไม่เปลี่ยน"
        )
    if dte is not None:
        if dte <= 1:
            parts.append("สัญญาใกล้หมดอายุ")
        else:
            parts.append(f"เหลืออายุประมาณ {_show(dte)} วัน")

    term = volatility.get("iv_term_structure") or []
    valid = [
        x for x in term
        if isinstance(x, dict) and _num(x.get("dte")) is not None and _num(x.get("iv")) is not None
    ]
    if len(valid) >= 2:
        valid = sorted(valid, key=lambda x: _num(x.get("dte")) or 0.0)
        near = _num(valid[0].get("iv"))
        far = _num(valid[-1].get("iv"))
        if near is not None and far is not None and near != far:
            parts.append("สัญญาใกล้หมดอายุมี IV สูงกว่า" if near > far else "สัญญาไกลกว่ามี IV สูงกว่า")

    return " ".join(parts) or "ยังไม่มีภาพความผันผวนที่ยืนยันได้"


def _why_now(state: dict[str, Any], path: dict[str, Any], parsed: dict[str, Any]) -> str:
    gamma = state.get("gamma") or {}
    upper = _node(path, "upper_node").get("level")
    lower = _node(path, "lower_node").get("level")
    net_gex = _num(gamma.get("net_gex"))

    if _num(upper) is not None and net_gex is not None and net_gex < 0:
        return f"ระดับ {_show(upper)} สำคัญเพราะ Gamma เป็นลบ ทำให้ถ้าราคาออกจากบริเวณนี้ การเคลื่อนไหวอาจเร่งขึ้น"
    if _num(lower) is not None and net_gex is not None and net_gex < 0:
        return f"ระดับ {_show(lower)} สำคัญเพราะ Gamma เป็นลบ ทำให้ถ้าราคาออกจากบริเวณนี้ การเคลื่อนไหวอาจเร่งลง"
    if _num(upper) is not None:
        return f"ระดับ {_show(upper)} สำคัญเพราะเป็นจุดที่ต้องเห็นการยืนราคา ก่อนเส้นทางถัดไปจะเปิด"
    if _num(lower) is not None:
        return f"ระดับ {_show(lower)} สำคัญเพราะเป็นจุดที่ต้องเห็นการรับหรือหลุดให้ชัด ก่อนประเมินทางต่อ"

    return "ตอนนี้ยังไม่มีระดับใกล้ราคาที่ข้อมูลยืนยันได้มากพอให้ใช้เป็นจุดชี้ขาด"


def _market_summary(
    parsed: dict[str, Any],
    state: dict[str, Any],
    path: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    sentence1 = _state_sentence(state, parsed, path)
    sentence2 = _mechanism_sentence(state)
    sentence3 = _conflict_sentence(state, evidence)
    sentence4 = _path_sentence(path)

    # A single narrative should sound like one analyst speaking, so omit
    # duplicate/empty sentences instead of filling fixed slots with metrics.
    candidates = [sentence1, sentence2, sentence3, sentence4]
    clean: list[str] = []
    seen: set[str] = set()
    for sentence in candidates:
        sentence = _clean(sentence)
        if not sentence or sentence in seen:
            continue
        seen.add(sentence)
        clean.append(sentence)
    return " ".join(clean[:4])


def _legacy_market_read(state: dict[str, Any], parsed: dict[str, Any], path: dict[str, Any], ai_result: dict[str, Any]) -> str:
    decision = _decision(state)
    structural = str(decision.get("structural_bias") or "").upper()
    confirmation = str(decision.get("confirmation_state") or "").upper()
    tactical = str(decision.get("tactical_direction") or "").upper()
    if confirmation == "CONFIRMED":
        side = "ขาขึ้น" if structural == "BULLISH" else "ขาลง" if structural == "BEARISH" else "setup ที่ยืนยัน"
        return f"โครงสร้างหลักและพฤติกรรมราคาสอดคล้องกันแล้ว จึงมี{side}ที่ยืนยันจากข้อมูลราคา"
    if structural == "MIXED":
        return "โครงสร้างหลักยังขัดกัน และตอนนี้ควรรอให้ราคายอมรับอยู่ด้านใดด้านหนึ่งก่อน"
    if tactical.endswith("_AGAINST_STRUCTURE"):
        side = "ขาลง" if structural == "BEARISH" else "ขาขึ้น"
        return f"ภาพหลักยังเป็น{side} แต่ระยะสั้นกำลังสวน จึงยังไม่ถือว่าเป็นการกลับทิศ"
    if structural in {"BULLISH", "BEARISH"}:
        side = "ขาขึ้น" if structural == "BULLISH" else "ขาลง"
        return f"โครงสร้างหลักยังเป็น{side} แต่ยังไม่มี price confirmation"
    fallback = _friendly_text(ai_result.get("market_overview"))
    return fallback or "ยังไม่มีภาพตลาดที่ยืนยันได้"


def build_customer_narrative(parsed: dict[str, Any], ai_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one coherent market story plus compact supporting sections."""
    ai_result = ai_result or {}
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    evidence = raw.get("evidence_fusion_v52") or {}
    path = _path(parsed, ai_result)

    summary = _market_summary(parsed, state, path, evidence)
    if not summary:
        summary = _legacy_market_read(state, parsed, path, ai_result)

    technical_llm = _friendly_text(ai_result.get("market_microstructure"))
    technical = technical_llm or _technical_sentence(state) or "ยังไม่มีข้อมูล Technical ที่เพียงพอ"

    macro = _friendly_text(ai_result.get("macro"))
    if not macro:
        macro = _fresh_news_sentence(parsed)

    current = _current(parsed, path)
    compact = compact_market_flow(current, path, state) if current is not None and path else {
        "read": summary,
        "flow": "ยังไม่มี conditional path ที่ยืนยันได้",
    }

    return {
        "summary": summary,
        "market_read": _legacy_market_read(state, parsed, path, ai_result),
        "why_now": _why_now(state, path, parsed),
        "flow_statement": _mechanism_sentence(state),
        "oi_positioning": _oi_sentence(state),
        "volatility": _volatility_text(state, parsed),
        "confirmation": _conflict_sentence(state, evidence) or "ตอนนี้ยังไม่มี conflict สำคัญเพิ่มเติมจากข้อมูลที่มี",
        "technical": technical,
        "macro_news": macro,
        "history": _history_sentence(state),
        "path_read": _path_sentence(path) or compact.get("flow") or "ยังไม่มี conditional path",
        "invalidation": _invalidation_sentence(state, path),
        "writing_meta": {
            "style": "human_thai_market_analyst",
            "max_summary_sentences": 4,
            "primary_evidence_families": [
                "PRICE_STRUCTURE",
                "OPTIONS_POSITIONING",
                "VOLATILITY",
                "TECHNICAL_TIMING",
                "EVENT",
            ],
            "rules": [
                "relationship_over_metric_list",
                "now_before_history",
                "one_primary_mechanism",
                "one_material_conflict",
                "conditional_path_before_trade_plan",
            ],
        },
    }
