from commercial.release_gate import GateEvidence, GateState, REQUIRED_GATES, evaluate_release

def passed_gates():
    return tuple(
        GateEvidence(
            name,
            GateState.PASS,
            evidence_ref=f"fixture:{name}",
            executed_at="2026-10-01T00:00:00Z",
            environment="test",
        )
        for name in REQUIRED_GATES
    )

def test_release_blocks_when_any_required_gate_is_missing():
    decision = evaluate_release(
        [GateEvidence(name, GateState.PASS) for name in REQUIRED_GATES[:-1]]
    )
    assert decision.allowed is False
    assert REQUIRED_GATES[-1] in decision.failed_gates

def test_release_blocks_non_pass_gate():
    gates = list(passed_gates())
    gates[0] = GateEvidence("data_rights", GateState.LEGAL_REVIEW_REQUIRED)
    decision = evaluate_release(gates)
    assert decision.allowed is False
    assert "data_rights" in decision.failed_gates

def test_release_keeps_live_trading_disabled():
    decision = evaluate_release(passed_gates(), live_trading_enabled=True)
    assert decision.allowed is False
    assert "live_trading" in decision.failed_gates

def test_all_required_gates_pass_ready_for_review():
    decision = evaluate_release(passed_gates())
    assert decision.allowed is True
    assert decision.status == "READY_FOR_CONTROLLED_PRODUCTION_REVIEW"
