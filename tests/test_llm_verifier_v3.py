import pytest
from src.llm_verifier import verify_output, LLMVerificationError

def env():
    return {
        "product":"GC","data_status":"VALID","as_of":"2026-10-02T06:00:00+00:00",
        "input_refs":["E1"],"evidence":{"E1":{"price":4180,"gex":123.4}}
    }

def base():
    return {
      "analysis_id":"A1","as_of":"2026-10-02T05:00:00+00:00","product":"GC",
      "regime":{"state":"RANGE","confidence":0.8,"evidence_refs":["E1"],"limitations":[]},
      "facts":[{"id":"F1","domain":"PRICE","statement":"Price 4180","evidence_refs":["E1"],"confidence":1}],
      "interpretations":[],"conflicts":[],"scenarios":[],"trade_plan":{"state":"WAIT","long":{},"short":{}},
      "why_not_long":[],"why_not_short":[],"uncertainties":[],"narrative":{"summary":"Price 4180"},
      "evidence_refs":["E1"]
    }

def test_v3_rejects_unsupported_numeric_claim_in_narrative():
    o=base(); o["narrative"]["summary"]="Price is 4199"
    with pytest.raises(LLMVerificationError,match="UNSUPPORTED_NUMERIC_CLAIMS"):
        verify_output(envelope=env(),output=o,schema=None)

def test_v3_rejects_unsupported_dealer_assertion():
    o=base(); o["narrative"]["summary"]="Dealer is short gamma"
    with pytest.raises(LLMVerificationError,match="FORBIDDEN_EXECUTION_CLAIM|FORBIDDEN"):
        verify_output(envelope=env(),output=o,schema=None)
