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


def record_from_payload(payload: dict[str, Any], positioning: dict[str, Any] | None = None) -> MarketStateRecord:
    """Rehydrate a serialized canonical MarketState without recalculating quant metrics."""
    state = MarketState(
        symbol=str(payload["symbol"]),
        price=payload.get("price"),
        as_of=datetime.fromisoformat(str(payload["as_of"]).replace("Z", "+00:00")),
        oi=payload.get("oi"),
        oi_change=payload.get("oi_change"),
        gex=payload.get("gex"),
        dex=payload.get("dex"),
        iv=payload.get("iv"),
        realized_vol=payload.get("realized_vol"),
        gamma_flip=payload.get("gamma_flip"),
        call_wall=payload.get("call_wall"),
        put_wall=payload.get("put_wall"),
        positioning_regime=payload.get("positioning_regime") or "UNKNOWN",
        volatility_regime=payload.get("volatility_regime") or "UNKNOWN",
        data_quality=float(payload.get("data_quality") or 0.0),
        data_age_seconds=payload.get("data_age_seconds"),
        data_status=DataStatus(payload.get("data_status") or "UNAVAILABLE"),
        dataset_version=payload.get("dataset_version") or "unknown",
        calculation_version=payload.get("calculation_version") or "unknown",
        sign_convention=payload.get("sign_convention"),
        gamma_source=payload.get("gamma_source"),
        assumptions=tuple(payload.get("assumptions") or ()),
        evidence=tuple(payload.get("evidence") or ()),
    )
    return MarketStateRecord(state=state, positioning=positioning or {})


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
