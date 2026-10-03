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
    assert "GOLD MARKET" in message
    assert "Futures 4,300.00 | CFD 4,297.00" in message
    assert "MARKET READ" in message
    assert "WHY NOW" in message
    assert "TECHNICAL" in message
    assert "MACROECONOMIC / NEWS" in message


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


def test_telegram_renders_three_text_message_sections():
    from src import telegram
    parsed = {
        "future_price": 4214.1,
        "cfd_price": 4186.58736,
        "dte": 0.34,
        "raw_series": {
            "totals": {"open_interest_view_put": 3996, "open_interest_view_call": 3048},
            "multi_expiry_gamma": {
                "columns": [{"code": "OG1V6"}, {"code": "G1M6"}, {"code": "G1T6"}, {"code": "G1W6"}, {"code": "G1R6"}, {"code": "OG2V6"}, {"code": "G2M6"}],
            },
            "multi_expiry_gamma_zones": {
                "highest_positive_gamma": 4215,
                "highest_negative_gamma": 4200,
            },
        },
    }
    ai = {
        "analysis_status": "DEGRADED", "bias": "WAIT",
        "what": "WHAT text",
        "why": "WHY text",
        "positioning": "POSITIONING text",
        "levels": {
            "resistance_far": "4232.48736", "resistance_main": "4222.48736",
            "resistance_current": "4197.48736", "support_current": "4172.48736",
            "support_main": "4152.48736", "support_deep": "4122.48736",
        },
        "scenarios": {"bull": "bull", "bear": "bear", "sideway": "sideway"},
        "trade_plan": {
            "status": "CONDITIONAL", "setup": "รอการยืนยัน",
            "confirmation": "ยืนยัน", "invalidation": "invalid", "risk_note": "risk",
            "long_trigger": 4197.48736, "long_stop": 4172.48736,
            "long_tp1": 4232.48736, "long_tp2": 4242.48736, "long_tp3": 4252.48736,
            "short_trigger": 4172.48736, "short_stop": 4197.48736,
            "short_tp1": 4152.48736, "short_tp2": 4122.48736, "short_tp3": 4112.48736,
        },
    }
    m3 = telegram._format_analysis_message(parsed, ai)
    m4 = telegram._format_levels_message(parsed, ai)
    m5 = telegram._format_trade_plan_message(parsed, ai)
    assert "WHAT text" in m3 and "WHY text" in m3 and "POSITIONING text" in m3
    assert "4,232.49" in m4 and "GAMMA TERM STRUCTURE" in m4 and "7" in m4 and "🟢" in m4 and "🔴" in m4 and "🟡" in m4
    assert "Status: <b>CONDITIONAL</b>" in m5
    assert "Bias:" in m5
    assert "Trigger:" in m5
    assert "SL:" in m5
    assert "TP1:" in m5
    assert "TP2:" in m5


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
    assert "GOLD MARKET" in message
    assert "GOLD OI UPDATE" not in message
    assert "DEGRADED" in message


def test_telegram_escapes_dynamic_trade_level_text():
    from src import telegram
    parsed = {}
    ai = {
        "bias": "WAIT",
        "trade_plan": {
            "status": "CONDITIONAL",
            "long_trigger": "<4180",
            "long_stop": "4100",
            "long_tp1": 4200,
            "long_tp2": 4250,
            "long_tp3": 4300,
            "short_trigger": 4100,
            "short_stop": 4180,
            "short_tp1": 4050,
            "short_tp2": 4000,
            "short_tp3": 3950,
        },
    }
    message = telegram._format_trade_plan_message(parsed, ai)
    assert "&lt;4180" in message
    assert "<4180" not in message


def test_trade_plan_ladders_are_directionally_monotonic():
    from src.market_state import normalize_analyst_output

    parsed = {
        "future_price": 4162.30,
        "cfd_price": 4137.63829,
        "basis_diff": 24.66171,
        "raw_series": {
            "gex": {
                "rows": [{"strike": x, "net_gex": 1.0} for x in (4150, 4155, 4160, 4165, 4170, 4175, 4180, 4185)],
                "call_wall": 4170,
                "put_wall": 4155,
                "net_gex": 8.0,
            },
            "multi_expiry_gamma_zones": {
                "highest_positive_gamma": 4175,
                "highest_negative_gamma": 4150,
            },
        },
    }
    parsed["raw_series"]["market_state"] = {
        "levels": {
            "resistance_far": 4162.73829,
            "resistance_main": 4145.33829,
            "resistance_current": 4140.33829,
            "support_current": 4132.33829,
            "support_main": 4130.33829,
            "support_deep": 4120.33829,
        },
        "gamma": {"gamma_mean": 4137.63829, "negative_zone": 4125.0, "positive_zone": 4150.0},
        "history": {},
        "cfd_complete": True,
    }
    ai = normalize_analyst_output(parsed, {}, {"bias": "SELL", "analysis_status": "CONFIRMED"})
    trade = ai["trade_plan"]
    assert trade["long_stop"] < trade["long_trigger"] < trade["long_tp1"] < trade["long_tp2"] < trade["long_tp3"]
    assert trade["short_tp3"] < trade["short_tp2"] < trade["short_tp1"] < trade["short_trigger"] < trade["short_stop"]


def test_invalid_trade_plan_fails_closed_instead_of_swapping_levels():
    from src.market_state import _validate_or_clear_trade_plan

    plan = {
        "long_trigger": 4140.28, "long_stop": 4130.28,
        "long_tp1": 4130.45, "long_tp2": 4130.28, "long_tp3": 4125.28,
        "short_trigger": 4130.28, "short_stop": 4140.28,
        "short_tp1": 4130.45, "short_tp2": 4130.28, "short_tp3": 4125.28,
        "status": "CONDITIONAL", "direction": "SELL",
    }
    out = _validate_or_clear_trade_plan(plan)
    assert out["status"] == "NO_TRADE"
    assert out["direction"] == "WAIT"
    assert out["long_tp1"] is None and out["short_tp1"] is None
