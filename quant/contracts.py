from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
from typing import Optional


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


def normalize_option_type(value: str | OptionType | None) -> OptionType | None:
    if value is None:
        return None
    if isinstance(value, OptionType):
        return value
    normalized = str(value).strip().upper()
    if normalized in {"C", "CALL"}:
        return OptionType.CALL
    if normalized in {"P", "PUT"}:
        return OptionType.PUT
    raise ValueError(f"UNKNOWN_OPTION_TYPE:{value}")


def canonical_id(*parts: object) -> str:
    payload = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class Instrument:
    symbol: str
    root: str
    exchange: str
    asset_class: str
    currency: str | None = None
    timezone: str = "UTC"

    @property
    def instrument_id(self) -> str:
        return canonical_id("instrument", self.exchange, self.root, self.symbol)


@dataclass(frozen=True)
class Future:
    instrument_id: str
    contract_code: str
    root: str
    exchange: str
    expiration: datetime | date | None
    multiplier: float | None
    currency: str | None
    tick_size: float | None = None
    settlement_type: str | None = None

    @property
    def future_id(self) -> str:
        return canonical_id(
            "future",
            self.exchange,
            self.contract_code,
            self.expiration,
        )


@dataclass(frozen=True)
class Expiration:
    underlying: str
    expiry: datetime
    timezone: str = "UTC"
    bucket: str = "UNKNOWN"
    is_weekly: bool = False
    is_monthly: bool = False

    @property
    def expiration_id(self) -> str:
        return canonical_id(
            "expiration",
            self.underlying,
            self.expiry.isoformat(),
            self.timezone,
        )

    @property
    def dte_days(self) -> float:
        now = datetime.now(self.expiry.tzinfo) if self.expiry.tzinfo else datetime.utcnow()
        return max(0.0, (self.expiry - now).total_seconds() / 86400.0)


@dataclass(frozen=True)
class Strike:
    underlying: str
    value: float

    @property
    def strike_id(self) -> str:
        return canonical_id("strike", self.underlying, f"{self.value:.12g}")


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    root: str
    exchange: str
    underlying: str
    option_type: OptionType | None
    expiration: date | None
    strike: float | None
    multiplier: float | None
    currency: str | None
    settlement_type: str | None
    source: str
    source_contract_code: str | None = None
    instrument_id: str | None = None
    future_id: str | None = None
    expiration_id: str | None = None
    strike_id: str | None = None

    @property
    def is_option(self) -> bool:
        return self.option_type is not None

    @property
    def canonical_key(self) -> str:
        expiry = self.expiration.isoformat() if self.expiration else "UNKNOWN_EXPIRY"
        strike = f"{self.strike:g}" if self.strike is not None else "UNKNOWN_STRIKE"
        side = self.option_type.value if self.option_type else "FUTURE"
        return f"{self.exchange}:{self.root}:{self.underlying}:{expiry}:{strike}:{side}"

    @property
    def canonical_id(self) -> str:
        return canonical_id("option", self.canonical_key)


# Backward-compatible name. New code should use OptionContract.
Contract = OptionContract
