"""Regression guards for customer-facing narrative quality.

These tests protect deterministic-source precedence and a small set of
anti-AI-slop contracts: do not echo unverified LLM conclusions over the
deterministic market state, do not invent price data when none exists, and
preserve legacy analyst text when the canonical narrative is absent.
"""
from src.customer_narrative import build_customer_narrative
from src import telegram


def _decision_fixture():
    return {
        "raw_series": {
            "market_state": {
                "decision": {
                    "structural_bias": "BEARISH",
                    "tactical_direction": "BULLISH_AGAINST_STRUCTURE",
                    "confirmation_state": "NOT_CONFIRMED",
                    "decision_state": "WAIT_BEARISH",
                },
                "flow": {},
                "volatility": {},
                "technical": {
                    "h4": {"trend": "bearish"},
                    "h1": {"trend": "bearish"},
                },
            }
        }
    }


def test_customer_story_keeps_deterministic_read_without_spot():
    out = build_customer_narrative(
        _decision_fixture(),
        {
            "analysis_status": "CONFIRMED",
            "market_overview": "confirmed sell setup",
            "bias": "SELL",
        },
    )
    assert "ภาพหลักยังเป็นขาลง" in out["market_read"]
    assert "ฟื้นตัวระยะสั้น" in out["market_read"]
    assert "confirmed sell" not in out["market_read"].lower()
    assert "ไม่มีราคาปัจจุบัน" not in out["market_read"]


def test_telegram_preserves_legacy_analyst_fields_when_canonical_story_is_absent():
    parsed = {
        "future_price": 4214.1,
        "cfd_price": 4186.58736,
        "dte": 0.34,
        "raw_series": {},
    }
    ai = {
        "analysis_status": "DEGRADED",
        "bias": "WAIT",
        "what": "WHAT text",
        "why": "WHY text",
        "positioning": "POSITIONING text",
    }
    message = telegram._format_analysis_message(parsed, ai)
    assert "WHAT text" in message
    assert "WHY text" not in message
    assert "POSITIONING text" not in message


def test_customer_story_does_not_claim_direct_dealer_intent():
    parsed = {
        "cfd_price": 4000,
        "raw_series": {
            "market_state": {
                "decision": {
                    "structural_bias": "BEARISH",
                    "tactical_direction": "NEUTRAL",
                    "confirmation_state": "NOT_CONFIRMED",
                },
                "path": {"current_price": 4000},
                "gamma": {"net_gex": -100},
                "flow": {},
                "technical": {},
            }
        },
    }
    out = build_customer_narrative(parsed, {})
    assert "ไม่ได้หมายความว่าเรารู้ว่าผู้ดูแลสภาพคล่องตั้งใจจะดันหรือกดราคา" in out["market_read"]


def test_telegram_article_removes_raw_telemetry_and_keeps_distinct_analysis():
    parsed = {
        "cfd_price": 3993.70,
        "future_price": 4007.90,
        "basis_diff": 14.20,
        "vol": 16.96,
        "dte": 1.16,
        "observed_at": "2026-10-25T16:00:00+00:00",
        "raw_series": {"market_state": {"flow": {}, "gex": {}}},
    }
    ai = {
        "market_overview": "ภาพหลักยังเป็นขาลง แต่ระยะสั้นกำลังฟื้นตัว",
        "why": "Gamma เป็นลบ จึงทำให้การเคลื่อนไหวเมื่อหลุดระดับสำคัญมีโอกาสแรงขึ้น",
        "positioning": "OI เพิ่มทั้ง Put และ Call แต่ข้อมูลนี้ยังไม่บอก aggressor",
        "history_comparison": "1H: Price Δ UNKNOWN | OI Δ UNKNOWN",
        "macro": "TODAY: Price Δ 0.00 | IV Δ -0.24%",
    }
    message = telegram._format_analysis_message(parsed, ai)
    assert "1H:" not in message
    assert "TODAY:" not in message
    assert "ภาพหลักยังเป็นขาลง" in message
    assert "Gamma เป็นลบ" in message
