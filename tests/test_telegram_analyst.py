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
    assert "CFD <b>4,297.00</b> | FUTURES <b>4,300.00</b>" in message
    assert "BASIS <b>-</b> | IV <b>-</b> | DTE <b>1.38</b>" in message
    assert "ตอนนี้เกิดอะไรขึ้น" in message
    assert "ทำไมระดับนี้ถึงสำคัญ" in message
    assert "ข่าว / เศรษฐกิจ" in message
    assert "Options:" in message
    assert "TRADE PLAN" not in message


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
    assert "WHAT text" in m3
    assert "ตอนนี้เกิดอะไรขึ้น" in m3
    assert "ข่าว / เศรษฐกิจ" in m3
    assert "Current OI" not in m3
    assert "📍 KEY LEVELS — จุดสำคัญของตลาด" in m4
    assert "ยังไม่มีจุดสำคัญที่ข้อมูลยืนยันได้" in m4
    assert "R1" not in m4 and "S1" not in m4
    assert "Call Wall" not in m4
    assert "Put Wall" not in m4
    assert "<b>TRADE PLAN</b>" in m5
    assert "🛑 SL" in m5
    assert "BUY 1 — เบรกแนวต้าน" in m5 or "SELL 1 — ต้านไม่ผ่าน" in m5
    assert "แผนสำรอง" in m5
    assert "Entry:" in m5
    assert "โซน/Trigger:" in m5


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
    assert "GOLD MARKET" in message


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
                "rows": [{"strike": x, "net_gex": 1.0} for x in (4060, 4080, 4100, 4115, 4120, 4125, 4130, 4135, 4140, 4145, 4150, 4155, 4160, 4175, 4190, 4210, 4230)],
                "call_wall": 4170,
                "put_wall": 4155,
                "net_gex": 8.0,
            },
            "multi_expiry_gamma_zones": {
                "highest_positive_gamma": 4175,
                "highest_negative_gamma": 4150,
                "resistance_nodes": [4170, 4180, 4200],
                "support_nodes": [4150, 4125, 4100],
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
    from src.market_state import _deterministic_trade_levels, _valid_trade_ladder
    det = _deterministic_trade_levels(parsed, parsed["raw_series"]["market_state"]["levels"], parsed["raw_series"]["market_state"]["gamma"])
    trade = ai["trade_plan"]
    long_values = [trade.get(f"long_tp{i}") for i in range(1, 6) if trade.get(f"long_tp{i}") is not None]
    short_values = [trade.get(f"short_tp{i}") for i in range(1, 6) if trade.get(f"short_tp{i}") is not None]
    assert trade["long_stop"] < trade["long_trigger"]
    assert trade["short_trigger"] < trade["short_stop"]
    assert long_values and short_values
    assert all(trade["long_trigger"] < x for x in long_values)
    assert all(trade["short_trigger"] > x for x in short_values)
    assert all(a < b for a, b in zip(long_values, long_values[1:]))
    assert all(a > b for a, b in zip(short_values, short_values[1:]))


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


def test_trade_targets_use_source_strikes_not_gamma_mean():
    from src.market_state import normalize_analyst_output

    parsed = {
        "future_price": 4162.30,
        "cfd_price": 4137.63829,
        "basis_diff": 24.66171,
        "raw_series": {
            "gex": {
                "rows": [{"strike": x, "net_gex": 1.0} for x in (4060, 4080, 4100, 4105, 4110, 4115, 4120, 4125, 4130, 4135, 4140, 4145, 4150, 4155, 4160, 4165, 4170, 4175, 4180, 4185, 4190, 4210, 4230)],
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
    ai = normalize_analyst_output(parsed, {}, {"bias": "WAIT", "analysis_status": "CONFIRMED"})
    trade = ai["trade_plan"]

    # Triggers come from structural GEX walls, normalized to CFD.
    assert trade["long_trigger"] == 4145.33829
    assert trade["short_trigger"] == 4130.33829
    # Execution targets must be real source strikes with structural spacing;
    # Gamma Mean / gamma zones are context only.
    assert trade["long_tp1"] == 4150.33829
    assert trade["long_tp2"] in {4155.33829, 4160.33829}
    assert trade["long_tp3"] is not None
    assert trade["short_tp1"] == 4125.33829
    assert trade["short_tp2"] in {4120.33829, 4115.33829}
    assert trade["short_tp3"] is not None
    assert trade["long_tp1"] != 4137.63829
    assert trade["short_tp1"] != 4137.63829


def test_telegram_renders_support_reaction_long_setup():
    from src import telegram
    ai = {
        "bias": "SELL",
        "trade_plan": {
            "status": "CONDITIONAL",
            "execution_plan": {
                "state": "ARMED",
                "long": {"state": "ARMED", "trigger": 4137.88, "stop": 4132.88, "targets": [4147.88]},
                "long_support": {"state": "ARMED", "trigger": 4072.88, "stop": 4067.88, "targets": [4082.88]},
                "short": {"state": "ARMED", "trigger": 4137.88, "stop": 4142.88, "targets": [4132.88]},
            },
        },
    }
    message = telegram._format_trade_plan_message({}, ai)
    assert "BUY 2 — รับด้านล่าง" in message
    assert "โซน/Trigger:" in message and "4,072.88" in message
    assert "🛑 SL: <b>4,067.88</b>" in message
    assert "🎯 TP1: <b>4,082.88</b>" in message


def test_trade_execution_plan_exposes_primary_alternative_and_non_fill_trigger():
    from src.trade_plan_engine import build_trade_execution_plan

    state = {
        "price": {"cfd": 4120},
        "technical": {
            "h4": {"trend": "bearish"},
            "h1": {"trend": "bearish"},
            "m15": {"trend": "neutral"},
            "m5": {"trend": "neutral"},
        },
        "market_map": {
            "long_reclaim_trigger": 4135,
            "long_reclaim_stop": 4130,
            "long_reclaim_trade_targets": [4175],
            "long_support_trigger": 4100,
            "long_support_invalidation": 4095,
            "long_support_trade_targets": [4120],
            "short_rejection_trigger": 4135,
            "short_rejection_stop": 4140,
            "short_rejection_trade_targets": [4100],
            "short_breakdown_trigger": 4100,
            "short_breakdown_stop": 4105,
            "short_breakdown_trade_targets": [4075],
        },
        "action_zones": {
            "setups": {
                "breakout_retest_long": {"setup_type": "BREAKOUT_RETEST", "side": "LONG", "zone_price": 4135, "state": "APPROACHING"},
                "reversal_long": {"setup_type": "REVERSAL", "side": "LONG", "zone_price": 4100, "state": "WAIT"},
                "reversal_short": {"setup_type": "REVERSAL", "side": "SHORT", "zone_price": 4135, "state": "APPROACHING"},
                "breakout_retest_short": {"setup_type": "BREAKOUT_RETEST", "side": "SHORT", "zone_price": 4100, "state": "WAIT"},
            }
        },
        "decision": {"structural_bias": "BEARISH"},
        "order_flow": {},
    }
    plan = build_trade_execution_plan(state)

    assert plan["preferred_setup"] == "SELL_REJECTION"
    assert plan["primary_setup"]["route"] == "SELL_REJECTION"
    assert plan["alternative_setup"]["route"] == "BUY_BREAKOUT"
    assert plan["primary_setup"]["entry_mode"] == "AFTER_CONFIRMATION"
    assert plan["primary_setup"]["entry_reference_role"] == "TRIGGER_ZONE_NOT_FILL"
    assert plan["trade_permission"] in {"WAIT_CONFIRMATION", "WAIT_RISK"}


def test_telegram_four_route_plan_renders_tp1_to_tp5():
    from src import telegram

    ai = {
        "bias": "SELL",
        "trade_plan": {
            "execution_plan": {
                "state": "ARMED",
                "preferred_setup": "SELL_REJECTION",
                "preferred_action": "เด้งกลับต้าน → rejection → SELL",
                "long_reclaim": {
                    "state": "ARMED", "trigger": 4210, "stop": 4205,
                    "targets": [4215, 4220, 4225, 4230, 4235],
                    "action": "เบรกและยืนเหนือโซน → รีเทสต์ไม่หลุด → BUY",
                    "risk": {"status": "PASS"},
                },
                "long_support": {
                    "state": "ARMED", "trigger": 4190, "stop": 4185,
                    "targets": [4195, 4200, 4205, 4210, 4215],
                    "action": "แตะโซนรับ → reaction → BUY",
                    "risk": {"status": "PASS"},
                },
                "short_rejection": {
                    "state": "ARMED", "trigger": 4210, "stop": 4215,
                    "targets": [4205, 4200, 4195, 4190, 4185],
                    "action": "เด้งกลับต้าน → rejection → SELL",
                    "risk": {"status": "PASS"},
                },
                "short_breakdown": {
                    "state": "ARMED", "trigger": 4190, "stop": 4195,
                    "targets": [4185, 4180, 4175, 4170, 4165],
                    "action": "หลุดแนวรับ → รีเทสต์ไม่ผ่าน → SELL",
                    "risk": {"status": "PASS"},
                },
            }
        },
    }
    message = telegram._format_trade_plan_message({}, ai)
    assert "TP1:" in message
    assert "TP3:" in message or "TP5:" in message
    assert "TRADE PLAN" in message


def test_customer_narrative_is_plain_language_and_uses_evidence_relationships():
    from src import telegram

    parsed = {
        "future_price": 4136.70,
        "cfd_price": 4134.78,
        "basis_diff": 1.92,
        "dte": 0.55,
        "vol": 29.17,
        "raw_series": {
            "market_state": {
                "flow": {
                    "oi_put": 1209,
                    "oi_call": 491,
                    "oi_change_put": 188,
                    "oi_change_call": 189,
                    "source_churn_total": 23.83,
                },
                "volatility": {"iv": 29.17, "iv_change_1h": 0.8, "skew": 1.2},
                "gamma": {
                    "net_gex": -87310948.74,
                    "put_wall": 4123.08156,
                    "call_wall": 4223.08156,
                },
                "technical": {
                    "h4": {"trend": "bearish"},
                    "h1": {"trend": "mixed"},
                },
            }
        },
    }
    ai = {
        "analysis_status": "DEGRADED",
        "bias": "WAIT",
        "market_regime": "EVENT",
        "market_overview": "ราคายังแกว่งใกล้ระดับสำคัญและยังไม่มีการยืนยันทางใด",
        "why": "OI activity สองฝั่งเพิ่มขึ้น แต่ aggressor direction ยังไม่ชัด",
        "financial_engineering": "Negative Gamma เพิ่มโอกาสให้การเคลื่อนไหวแรงขึ้น",
        "market_microstructure": "H4 bearish แต่กรอบสั้นยังไม่ยืนยัน",
        "macro": "มีข่าวสำคัญที่ตลาดกำลังรอ",
    }
    message = telegram._format_analysis_message(parsed, ai)
    assert "ตอนนี้เกิดอะไรขึ้น" in message
    assert "ทำไมระดับนี้ถึงสำคัญ" in message
    assert "ข่าว / เศรษฐกิจ" in message
    assert "Current OI" not in message
    assert "OI Change" not in message
