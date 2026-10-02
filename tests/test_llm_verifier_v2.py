import pytest
from src.llm_verifier import verify_output, LLMVerificationError


def envelope():
    return {
        "product": "GC",
        "data_status": "VALID",
        "as_of": "2026-10-02T06:00:00+00:00",
        "input_refs": ["itb:oi:deterministic"],
        "evidence": {"itb:oi:deterministic": {"call_wall": 4400, "put_wall": 4200}},
    }


def test_v2_numeric_levels_are_checked_against_evidence():
    output = {
        "analysis_status": "CONFIRMED", "market_overview": "x", "what": "x", "why": "x", "positioning": "x",
        "levels": {
            "resistance_far": "4500", "resistance_main": "4400", "resistance_current": "4300",
            "support_current": "4250", "support_main": "4200", "support_deep": "4100",
        },
        "scenarios": {"bull": "x", "bear": "x", "sideway": "x"},
        "bias": "WAIT", "uncertainty": 0.3,
        "trade_plan": {"status": "NO_TRADE", "setup": "x", "confirmation": "x", "invalidation": "x", "risk_note": "x"},
        "evidence_refs": ["itb:oi:deterministic"], "data_limitations": [],
    }
    with pytest.raises(LLMVerificationError, match="UNSUPPORTED_NUMERIC_CLAIMS:.*4500"):
        verify_output(envelope=envelope(), output=output, schema=None)


def test_v2_accepts_thousands_separators_and_display_rounding():
    output = {
        "analysis_status": "CONFIRMED", "market_overview": "x", "what": "x", "why": "x", "positioning": "x",
        "levels": {
            "resistance_far": "4,400", "resistance_main": "4,400.00", "resistance_current": "4,200",
            "support_current": "4,200", "support_main": "4,200.0", "support_deep": "4,200",
        },
        "scenarios": {"bull": "x", "bear": "x", "sideway": "x"}, "bias": "WAIT", "uncertainty": 0.3,
        "trade_plan": {"status": "NO_TRADE", "setup": "x", "confirmation": "x", "invalidation": "x", "risk_note": "x"},
        "evidence_refs": ["itb:oi:deterministic"], "data_limitations": [],
    }
    result = verify_output(envelope=envelope(), output=output, schema=None)
    assert result["verdict"] == "PASS"


def test_v2_confidence_is_not_treated_as_market_number():
    output = {
        "analysis_status": "CONFIRMED", "market_overview": "x", "what": "x", "why": "x", "positioning": "x",
        "levels": {k: v for k, v in {
            "resistance_far": "4400", "resistance_main": "4400", "resistance_current": "4400",
            "support_current": "4200", "support_main": "4200", "support_deep": "4200",
        }.items()},
        "scenarios": {"bull": "x", "bear": "x", "sideway": "x"}, "bias": "WAIT", "uncertainty": 0.3,
        "trade_plan": {"status": "NO_TRADE", "setup": "x", "confirmation": "x", "invalidation": "x", "risk_note": "x"},
        "evidence_refs": ["itb:oi:deterministic"], "data_limitations": [],
    }
    result = verify_output(envelope=envelope(), output=output, schema=None)
    assert result["verdict"] == "PASS"
