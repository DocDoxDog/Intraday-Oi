"""V5 human-readable reasoning spine for Gold Market Intelligence.
The engine converts deterministic evidence into:
FACT -> WHY -> CONFLICT -> NEXT EVENT -> INVALIDATION -> ACTION.
"""
from __future__ import annotations
from typing import Any
VERSION = "reasoning-v5.1"

def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) else None

def _status(x: Any) -> str:
    return str(x or "UNKNOWN").upper()

def _fact(fid: str, label: str, value: Any, meaning: str, refs: list[str]) -> dict[str, Any]:
    return {"id": fid, "label": label, "value": value, "meaning": meaning,
            "evidence_refs": refs, "kind": "FACT"}

def _direction(state: dict[str, Any]) -> str:
    ms = state.get("market_state") or {}
    decision = ms.get("decision_framework") or {}
    for key in ("structural_bias", "bias", "direction"):
        v = _status(decision.get(key) or ms.get(key))
        if v in {"BULLISH", "BEARISH", "LONG", "SHORT"}:
            return "BULLISH" if v in {"BULLISH", "LONG"} else "BEARISH"
    conf = (state.get("technical_context") or {}).get("confirmation") or {}
    v = _status(conf.get("bias"))
    return v if v in {"BULLISH", "BEARISH"} else "UNKNOWN"

def _price(state: dict[str, Any]) -> float | None:
    return _num(state.get("cfd_price", state.get("future_price")))

def _levels(state: dict[str, Any]) -> dict[str, Any]:
    ms = state.get("market_state") or {}
    levels = ms.get("levels") or {}
    gex = (state.get("raw_series") or {}).get("gex") or {}
    return {"current": _price(state),
            "resistance": levels.get("resistance_current", levels.get("resistance")),
            "support": levels.get("support_current", levels.get("support")),
            "gamma_flip": gex.get("gamma_flip"), "call_wall": gex.get("call_wall"),
            "put_wall": gex.get("put_wall")}

def _evidence(state: dict[str, Any], history: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw = state.get("raw_series") or {}
    totals = raw.get("totals") or {}
    gex = raw.get("gex") or {}
    out: list[dict[str, Any]] = []
    if _price(state) is not None:
        out.append(_fact("price", "ราคาปัจจุบัน", _price(state),
                         "ใช้เป็นจุดอ้างอิงของทุก scenario", ["itb:oi:deterministic"]))
    if totals.get("open_interest_view_call") is not None or totals.get("open_interest_view_put") is not None:
        out.append(_fact("oi", "Open Interest",
                         {"call": totals.get("open_interest_view_call"), "put": totals.get("open_interest_view_put")},
                         "บอกโครงสร้างสถานะคงค้าง ไม่ได้บอกว่าใครเป็นผู้ซื้อ/ขาย",
                         ["itb:oi:deterministic"]))
    if gex.get("net_gex") is not None:
        out.append(_fact("gex", "Gamma",
                         {"net": gex.get("net_gex"), "flip": gex.get("gamma_flip"),
                          "call_wall": gex.get("call_wall"), "put_wall": gex.get("put_wall")},
                         "ใช้บอกบริบทการ dampen/amplify และระดับที่ตลาดอาจตอบสนอง",
                         ["itb:oi:deterministic"]))
    conf = (state.get("technical_context") or {}).get("confirmation") or {}
    if conf:
        out.append(_fact("technical", "Price confirmation",
                         {"bias": conf.get("bias"), "htf_aligned": conf.get("htf_aligned")},
                         "ใช้เป็นตัวตัดสิน timing ไม่ใช่ให้ indicator เดียวชนะหลักฐานทั้งหมด",
                         ["itb:oi:deterministic"]))
    if history:
        out.append(_fact("history", "History",
                         {"hour": bool(history.get("hour_ago")),
                          "today_count": history.get("today", {}).get("count", 0),
                          "yesterday_count": history.get("yesterday", {}).get("count", 0)},
                         "ใช้ดูการเปลี่ยน regime/acceleration โดยไม่สร้างตัวเลขย้อนหลังขึ้นเอง",
                         ["itb:oi:history"]))
    return out

def build_reasoning_pack(state: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    direction = _direction(state)
    levels = _levels(state)
    evidence = _evidence(state, history)
    conflicts: list[dict[str, Any]] = []
    gex = (state.get("raw_series") or {}).get("gex") or {}
    gex_net = _num(gex.get("net_gex"))
    if direction == "BULLISH" and gex_net is not None and gex_net < 0:
        conflicts.append({"id": "negative-gamma", "severity": "MEDIUM",
                          "text": "Bias ขึ้น แต่ Gamma ติดลบอาจทำให้การเคลื่อนไหวถูกขยาย — ต้องรอ price confirmation"})
    if direction == "BEARISH" and gex_net is not None and gex_net > 0:
        conflicts.append({"id": "positive-gamma", "severity": "MEDIUM",
                          "text": "Bias ลง แต่ Gamma เป็นบวกอาจลดความเร็วของการเคลื่อนไหว — อย่าเร่งเข้า"})
    conf = (state.get("technical_context") or {}).get("confirmation") or {}
    if direction != "UNKNOWN" and _status(conf.get("bias")) not in {"UNKNOWN", direction}:
        conflicts.append({"id": "technical-conflict", "severity": "HIGH",
                          "text": "โครงสร้างหลักกับ timing ระยะสั้นยังไม่ตรงกัน"})
    current = levels["current"]
    resistance = _num(levels["resistance"] or levels["call_wall"])
    support = _num(levels["support"] or levels["put_wall"])
    if current is None:
        status = "DATA_INSUFFICIENT"
    elif direction == "UNKNOWN":
        status = "WAIT"
    elif any(c["severity"] == "HIGH" for c in conflicts):
        status = "CONDITIONAL"
    else:
        status = "WAIT_FOR_CONFIRMATION"
    scenarios = [
        {"id": "LONG", "when": ["Break/เหนือแนวต้าน", "Acceptance หรือยืนได้",
                                "Retest ไม่หลุด", "Momentum/structure ยืนยัน"],
         "trigger": resistance, "invalidation": support,
         "action": "LONG SETUP" if resistance is not None else "WAIT"},
        {"id": "SHORT", "when": ["Break/หลุดแนวรับ", "Acceptance ด้านล่าง",
                                  "Retest ไม่ผ่าน", "Momentum/structure ยืนยัน"],
         "trigger": support, "invalidation": resistance,
         "action": "SHORT SETUP" if support is not None else "WAIT"},
    ]
    return {
        "version": VERSION, "status": status, "directional_context": direction,
        "one_line": ("ตลาดกำลังรอ confirmation มากกว่าการเดาทิศ"
                     if status != "DATA_INSUFFICIENT" else "ข้อมูลยังไม่พอสำหรับสร้าง thesis"),
        "reasoning_ladder": [
            {"step": 1, "name": "WHAT", "answer": "อ่าน state ปัจจุบันจาก price + structure + options"},
            {"step": 2, "name": "WHY", "answer": "เชื่อม evidence ที่เป็นอิสระ; แยก fact กับ inference"},
            {"step": 3, "name": "CONFLICT", "answer": "หา evidence ที่ค้าน thesis ก่อนเพิ่ม conviction"},
            {"step": 4, "name": "NEXT", "answer": "กำหนด event ที่ต้องเกิด ไม่ใช่แค่แตะราคา"},
            {"step": 5, "name": "INVALIDATION", "answer": "กำหนดเหตุการณ์ที่ทำให้ thesis ผิด"},
            {"step": 6, "name": "ACTION", "answer": "เลือก LONG/SHORT/WAIT แบบมีเงื่อนไข"},
        ],
        "evidence": evidence, "conflicts": conflicts, "levels": levels,
        "scenarios": scenarios,
        "guardrails": [
            "OI ไม่เท่ากับ traded volume", "OI/GEX ไม่ใช่ directional oracle",
            "LEVEL ไม่เท่ากับ TRIGGER", "ห้ามสร้างตัวเลขที่ไม่มีใน evidence",
            "ห้ามถือว่า LLM เป็น execution authority",
        ],
    }
