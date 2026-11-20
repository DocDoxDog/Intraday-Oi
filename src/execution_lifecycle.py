"""Safe trade lifecycle wrapper around the deterministic risk and paper fill layers.

The default lifecycle is PAPER. It never carries broker credentials.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from src.paper_execution import PaperFill, PaperOrder, Quote, evaluate_fill_quality, simulate_fill


@dataclass(frozen=True)
class ExecutionDecision:
    status: str
    reason: str
    order: PaperOrder | None = None


def arm_paper_order(
    route: dict[str, Any],
    *,
    symbol: str,
    order_id: str,
    quantity: float,
    submitted_at: str,
) -> ExecutionDecision:
    if not isinstance(route, dict):
        return ExecutionDecision("REJECTED", "INVALID_ROUTE")
    if not bool(route.get("execution_ready")):
        return ExecutionDecision("REJECTED", "EXECUTION_GATE_NOT_READY")
    risk = route.get("risk") or {}
    if str(risk.get("status") or "").upper() != "PASS":
        return ExecutionDecision("REJECTED", "RISK_GATE_NOT_PASS")
    side = "BUY" if str(route.get("side") or "").upper().startswith("LONG") else "SELL"
    entry = route.get("entry_reference", route.get("trigger"))
    stop = route.get("stop")
    targets = route.get("targets") or []
    target = targets[0] if targets else None
    if entry is None or stop is None:
        return ExecutionDecision("REJECTED", "MISSING_ENTRY_OR_STOP")
    return ExecutionDecision(
        "ARMED",
        "PAPER_ORDER_CREATED",
        PaperOrder(
            order_id,
            symbol,
            side,
            float(quantity),
            submitted_at,
            float(entry),
            float(stop),
            float(target) if target is not None else None,
        ),
    )


def fill_paper_order(
    order: PaperOrder,
    quote: Quote,
    *,
    latency_ms: int = 150,
    extra_slippage_ticks: float = 0.0,
    tick_size: float = 0.01,
) -> dict[str, Any]:
    fill: PaperFill = simulate_fill(
        order,
        quote,
        latency_ms=latency_ms,
        extra_slippage_ticks=extra_slippage_ticks,
        tick_size=tick_size,
    )
    return evaluate_fill_quality(fill, tick_size=tick_size)


def journal_event_payload(
    run_id: str,
    event_type: str,
    *,
    order: PaperOrder | None = None,
    fill: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"run_id": run_id, "event_type": event_type}
    if order:
        payload["order"] = asdict(order)
    if fill:
        payload["fill"] = dict(fill)
    return payload
