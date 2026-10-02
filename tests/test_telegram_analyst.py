from src.telegram import format_message
from src.line import format_message as format_line_message


def test_telegram_renders_canonical_v2_without_creating_trade_levels():
    parsed = {
        "future_price": 4300,
        "cfd_price": 4297,
        "dte": 1.38,
        "raw_series": {"gex": {"status": "ok", "gamma_flip": 4280, "call_wall": 4400, "put_wall": 4200}},
    }
    ai = {
        "analysis_status": "CONFIRMED",
        "what": "ราคายังอยู่ใกล้ 4297 และหลักฐาน GEX ชี้ไปที่โซน 4200–4400",
        "why": "GEX เป็น deterministic evidence จาก source รอบนี้",
        "positioning": "Call wall 4400 และ put wall 4200",
        "levels": {
            "resistance_far": "4400", "resistance_main": "4350", "resistance_current": "4300",
            "support_current": "4250", "support_main": "4200", "support_deep": "4100",
        },
        "scenarios": {
            "bull": "ยืนเหนือ 4300 แล้วติดตามการตอบสนองที่ 4350",
            "bear": "หลุด 4250 แล้วติดตาม 4200",
            "sideway": "ยังไม่มีการยืนยันการออกจากกรอบ",
        },
        "bias": "WAIT",
        "uncertainty": 0.3,
        "trade_plan": {
            "status": "NO_TRADE",
            "setup": "ยังไม่มี setup ที่ผ่าน gate",
            "confirmation": "รอ technical confirmation",
            "invalidation": "ยังไม่มี setup",
            "risk_note": "ห้ามสร้าง Entry/SL/TP จาก OI เพียงอย่างเดียว",
        },
        "evidence_refs": ["itb:oi:deterministic"],
        "data_limitations": ["OI ไม่ใช่ traded intraday volume"],
    }
    message = format_message(parsed, ai)
    assert "<b>WAIT</b>" in message
    assert "4300" in message
    assert "TRADE PLAN" in message
    assert "Entry" not in message
    assert "TP1" not in message
    assert "SL" not in message


def test_telegram_requires_explicit_authorized_chat_ids(monkeypatch):
    import pytest
    from src import telegram
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    with pytest.raises(RuntimeError, match="chat_ids"):
        telegram.send({}, {"market_overview": "x"}, chat_ids=None)


def test_product_identity_does_not_default_unknown_to_gc():
    import pytest
    from src.supabot_llm import _product
    with pytest.raises(Exception, match="PRODUCT_UNRESOLVED"):
        _product({"contract": "UNKNOWN PRODUCT 2030"})


def test_line_renders_canonical_analysis_without_local_trade_plan():
    parsed = {
        "future_price": 4300, "cfd_price": 4297, "dte": 1.38, "vol": 15.2,
        "raw_series": {"totals": {"open_interest_view_put": 100, "open_interest_view_call": 200}}
    }
    ai = {
        "market_overview": "หลักฐานยังไม่ยืนยันการเปิดสถานะ", "bias": "WAIT",
        "resistance_far": "4400", "resistance_main": "4350", "resistance_current": "4300",
        "support_current": "4250", "support_main": "4200", "support_deep": "4100",
        "bull_case": "ยืนเหนือ 4300", "bear_case": "หลุด 4250", "sideway_case": "อยู่ในกรอบ",
    }
    message = format_line_message(parsed, ai)
    assert "TRADE PLAN" not in message
    assert "Entry" not in message
    assert "TP1" not in message
    assert "SL" not in message


def test_degraded_v2_has_no_trade_levels():
    parsed = {"future_price": 4300, "raw_series": {"gex": {"call_wall": 4400, "put_wall": 4200}}}
    ai = {
        "analysis_status": "DEGRADED", "bias": "WAIT",
        "what": "ไม่มี analyst output ที่ผ่าน verification",
        "why": "จึงไม่ควรสร้างระดับเพิ่ม", "positioning": "UNKNOWN",
        "levels": {"resistance_far": None, "resistance_main": 4400, "resistance_current": None, "support_current": None, "support_main": 4200, "support_deep": None},
        "scenarios": {"bull": "รอ confirmation", "bear": "รอ confirmation", "sideway": "ข้อมูลไม่พอ"},
        "trade_plan": {"status": "NO_TRADE", "setup": "ไม่มี", "confirmation": "ไม่มี", "invalidation": "ไม่มี", "risk_note": "ห้ามสร้าง Entry/SL/TP จาก OI เพียงอย่างเดียว"},
        "evidence_refs": ["itb:oi:deterministic"], "data_limitations": ["LLM rejected"],
    }
    message = format_message(parsed, ai)
    assert "GOLD MARKET ANALYST V2" in message
    assert "GOLD OI UPDATE" not in message
    assert "NO_TRADE" in message
