from src.telegram import format_message, format_notification
from src.line import format_message as format_line_message


def test_telegram_uses_canonical_bias_and_does_not_create_trade_levels():
    parsed = {
        "future_price": 4300,
        "cfd_price": 4297,
        "dte": 1.38,
        "raw_series": {"gex": {"status": "ok", "gamma_flip": 4280, "call_wall": 4400, "put_wall": 4200}},
    }
    ai = {
        "market_overview": "ราคายังอยู่ใกล้ 4297 และหลักฐาน GEX ชี้ไปที่โซน 4200–4400",
        "resistance_far": "4400",
        "resistance_main": "4350",
        "resistance_current": "4300",
        "support_current": "4250",
        "support_main": "4200",
        "support_deep": "4100",
        "bull_case": "ยืนเหนือ 4300 แล้วติดตามการตอบสนองที่ 4350",
        "bear_case": "หลุด 4250 แล้วติดตาม 4200",
        "sideway_case": "ยังไม่มีการยืนยันการออกจากกรอบ",
        "bias": "WAIT",
        "uncertainty": 0.3,
        "evidence_refs": ["itb:oi:deterministic"],
        "data_limitations": ["OI ไม่ใช่ traded intraday volume"],
    }

    message = format_message(parsed, ai)
    notification = format_notification(parsed, ai)

    assert "<b>WAIT</b>" in message
    assert "4300" in message
    assert "Entry" not in message
    assert "TP1" not in message
    assert "SL" not in message
    assert "Bias: <b>WAIT</b>" in notification


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
        "future_price": 4300,
        "cfd_price": 4297,
        "dte": 1.38,
        "vol": 15.2,
        "raw_series": {"totals": {"open_interest_view_put": 100, "open_interest_view_call": 200}}
    }
    ai = {
        "market_overview": "หลักฐานยังไม่ยืนยันการเปิดสถานะ",
        "bias": "WAIT",
        "resistance_far": "4400",
        "resistance_main": "4350",
        "resistance_current": "4300",
        "support_current": "4250",
        "support_main": "4200",
        "support_deep": "4100",
        "bull_case": "ยืนเหนือ 4300",
        "bear_case": "หลุด 4250",
        "sideway_case": "อยู่ในกรอบ",
    }
    message = format_line_message(parsed, ai)
    assert "TRADE PLAN" not in message
    assert "Entry" not in message
    assert "TP1" not in message
    assert "SL" not in message
