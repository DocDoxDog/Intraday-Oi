"""Deterministic paper-execution and fill-quality simulator.

Execution assumptions are measured separately from alpha.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Quote:
    timestamp: str
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return max(0.0, self.ask - self.bid)


@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    symbol: str
    side: str
    quantity: float
    submitted_at: str
    entry_reference: float
    stop: float | None = None
    target: float | None = None
    limit_price: float | None = None


@dataclass(frozen=True)
class PaperFill:
    order_id: str
    filled_at: str
    requested_price: float
    fill_price: float
    quantity: float
    spread_cost: float
    slippage_cost: float
    latency_ms: int


def simulate_fill(
    order: PaperOrder,
    quote: Quote,
    *,
    latency_ms: int = 150,
    extra_slippage_ticks: float = 0.0,
    tick_size: float = 0.01,
) -> PaperFill:
    side = order.side.upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if quote.bid <= 0 or quote.ask < quote.bid:
        raise ValueError("invalid quote")
    requested = float(order.limit_price if order.limit_price is not None else order.entry_reference)
    executable = quote.ask if side == "BUY" else quote.bid
    marketable = order.limit_price is None or (
        side == "BUY" and requested >= quote.ask
    ) or (
        side == "SELL" and requested <= quote.bid
    )
    if not marketable:
        executable = requested
    slippage = abs(executable - requested)
    slippage += max(0.0, float(extra_slippage_ticks)) * max(0.0, float(tick_size))
    spread_cost = abs(executable - quote.mid)
    if extra_slippage_ticks:
        if side == "BUY":
            executable += extra_slippage_ticks * tick_size
        else:
            executable -= extra_slippage_ticks * tick_size
    now = datetime.fromisoformat(quote.timestamp.replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    filled_at = now.timestamp() + max(0, int(latency_ms)) / 1000.0
    filled_dt = datetime.fromtimestamp(filled_at, tz=timezone.utc).isoformat()
    return PaperFill(
        order_id=order.order_id,
        filled_at=filled_dt,
        requested_price=requested,
        fill_price=executable,
        quantity=order.quantity,
        spread_cost=round(spread_cost, 8),
        slippage_cost=round(abs(executable - requested), 8),
        latency_ms=max(0, int(latency_ms)),
    )


def evaluate_fill_quality(fill: PaperFill, *, tick_size: float = 0.01) -> dict[str, Any]:
    total_cost = fill.spread_cost + fill.slippage_cost
    ticks = total_cost / tick_size if tick_size > 0 else None
    return {
        **asdict(fill),
        "total_execution_cost": total_cost,
        "total_cost_ticks": ticks,
        "quality": (
            "GOOD" if total_cost <= tick_size * 2 else
            "WATCH" if total_cost <= tick_size * 5 else
            "POOR"
        ),
    }
