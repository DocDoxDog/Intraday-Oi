from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Protocol

from quant.market_state import build_market_state
from quant.models import DataStatus, MarketState
from quant.serialization import to_jsonable


@dataclass(frozen=True)
class MarketStateRecord:
    state: MarketState
    positioning: dict[str, Any]


class MarketStateRepository(Protocol):
    def get(self, symbol: str) -> MarketStateRecord | None: ...
    def put(self, record: MarketStateRecord) -> None: ...


class InMemoryMarketStateRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._rows: dict[str, MarketStateRecord] = {}

    def get(self, symbol: str) -> MarketStateRecord | None:
        with self._lock:
            return self._rows.get(symbol.upper())

    def put(self, record: MarketStateRecord) -> None:
        with self._lock:
            self._rows[record.state.symbol.upper()] = record


def empty_market_state(symbol: str, *, reason: str = "MARKET_STATE_NOT_AVAILABLE") -> MarketStateRecord:
    now = datetime.now(timezone.utc)
    state = build_market_state(
        symbol=symbol.upper(),
        price=None,
        as_of=now,
        positioning={
            "oi": {"total_oi": None, "oi_change_total": None},
            "gex": {"status": "unavailable", "calculation_version": "unknown"},
            "dex": {"status": "unavailable"},
            "assumptions": ("state_unavailable",),
        },
        data_quality=0.0,
        data_status=DataStatus.UNAVAILABLE,
        data_age_seconds=None,
        dataset_version="unknown",
    )
    return MarketStateRecord(
        state=state,
        positioning={"status": "unavailable", "reason": reason},
    )


def record_to_response(record: MarketStateRecord) -> dict[str, Any]:
    state = record.state
    return {
        "symbol": state.symbol,
        "as_of": state.as_of,
        "data_age_seconds": state.data_age_seconds,
        "data_age": state.data_age_seconds,
        "data_quality": state.data_quality,
        "data_status": state.data_status.value,
        "source": "canonical_quant",
        "dataset_version": state.dataset_version,
        "calculation_version": state.calculation_version,
        "data": {
            "market_state": to_jsonable(state),
            "positioning": to_jsonable(record.positioning),
        },
    }
