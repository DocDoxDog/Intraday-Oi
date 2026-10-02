from src.llm_verifier import verify_output


def _envelope(level=3085.0):
    return {
        "input_refs": ["itb:oi:deterministic"],
        "data_status": "VALID",
        "product": "GC",
        "as_of": "2026-10-02T14:00:00+00:00",
        "evidence": {
            "itb:oi:deterministic": {
                "observed_at": "2026-10-02T14:00:00+00:00",
                "payload": {"future_price": 4200.0},
            }
        },
        "input_payload": {
            "deterministic_levels": [
                {"id": "market_state:test", "price": level}
            ]
        },
    }


def test_governed_deterministic_level_is_supported_without_extra_numeric_evidence_ref():
    envelope = _envelope()
    output = {
        "evidence_refs": ["itb:oi:deterministic"],
        "levels": {"resistance": "3085.00"},
        "trade_plan": {"status": "CONDITIONAL"},
    }
    result = verify_output(envelope=envelope, output=output, schema=None)
    assert result["verdict"] == "PASS"
    assert result["numeric_claims_valid"] is True


def test_ungoverned_numeric_price_is_rejected():
    envelope = _envelope(3085.0)
    output = {
        "evidence_refs": ["itb:oi:deterministic"],
        "levels": {"resistance": "3086.00"},
        "trade_plan": {"status": "CONDITIONAL"},
    }
    try:
        verify_output(envelope=envelope, output=output, schema=None)
    except Exception as exc:
        assert "UNSUPPORTED_NUMERIC_CLAIMS:3086.00" in str(exc)
    else:
        raise AssertionError("unsupported numeric claim was accepted")
