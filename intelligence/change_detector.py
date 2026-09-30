from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketChange:
    field: str
    previous: Any
    current: Any
    changed: bool
    reason: str


def detect_changes(previous, current) -> tuple[MarketChange, ...]:
    fields = (
        "price", "oi", "oi_change", "gex", "dex", "iv", "realized_vol",
        "gamma_flip", "call_wall", "put_wall",
        "positioning_regime", "volatility_regime", "data_status",
    )
    out = []
    for field in fields:
        old = getattr(previous, field, None)
        new = getattr(current, field, None)
        changed = old != new
        out.append(
            MarketChange(
                field=field,
                previous=old,
                current=new,
                changed=changed,
                reason=f"{field}_changed" if changed else f"{field}_unchanged",
            )
        )
    return tuple(out)
