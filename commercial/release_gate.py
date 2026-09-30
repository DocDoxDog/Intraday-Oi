from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

class GateState(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    NOT_VERIFIED = "NOT_VERIFIED"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    PENDING = "PENDING"

REQUIRED_GATES: tuple[str, ...] = (
    "data_rights",
    "source_timestamps",
    "canonical_market_state",
    "ci_green",
    "ai_trader_baseline",
    "tenant_e2e",
    "customer_channel_e2e",
    "aws_runtime",
    "payment_approval",
    "legal_regulatory",
    "oos_walkforward",
    "paper_gate",
    "load_test",
)

def _state_value(state: GateState | str) -> str:
    return state.value if isinstance(state, GateState) else str(state)

@dataclass(frozen=True)
class GateEvidence:
    name: str
    state: GateState | str
    evidence_ref: str | None = None
    executed_at: str | None = None
    commit_sha: str | None = None
    environment: str | None = None
    note: str | None = None
    required: bool = True

    @property
    def is_pass(self) -> bool:
        return _state_value(self.state) == GateState.PASS.value

@dataclass(frozen=True)
class ReleaseDecision:
    allowed: bool
    status: str
    failed_gates: tuple[str, ...]
    reasons: tuple[str, ...]

def evaluate_release(gates: Iterable[GateEvidence], *, live_trading_enabled: bool = False) -> ReleaseDecision:
    by_name = {gate.name: gate for gate in gates}
    failed: list[str] = []
    reasons: list[str] = []
    if live_trading_enabled:
        failed.append("live_trading")
        reasons.append("LIVE_TRADING_MUST_REMAIN_DISABLED_FOR_COMMERCIAL_PHASE")
    for name in REQUIRED_GATES:
        gate = by_name.get(name)
        if gate is None:
            failed.append(name)
            reasons.append(f"MISSING_REQUIRED_GATE:{name}")
            continue
        if not gate.is_pass:
            failed.append(name)
            reasons.append(f"GATE_NOT_PASS:{name}:{_state_value(gate.state)}")
    if failed:
        return ReleaseDecision(False, "BLOCKED", tuple(dict.fromkeys(failed)), tuple(dict.fromkeys(reasons)))
    return ReleaseDecision(True, "READY_FOR_CONTROLLED_PRODUCTION_REVIEW", (), ())

def assert_release_ready(gates: Iterable[GateEvidence], *, live_trading_enabled: bool = False) -> ReleaseDecision:
    decision = evaluate_release(gates, live_trading_enabled=live_trading_enabled)
    if not decision.allowed:
        raise RuntimeError("COMMERCIAL_RELEASE_BLOCKED:" + ",".join(decision.failed_gates))
    return decision
