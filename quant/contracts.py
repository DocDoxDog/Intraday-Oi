from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import hashlib


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
        return canonical_id("future", self.exchange, self.contract_code, self.expiration)


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
        return canonical_id("expiration", self.underlying, self.expiry.isoformat(), self.timezone)


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

    @property
    def resolution_status(self) -> str:
        required = (
            self.instrument_id,
            self.future_id,
            self.expiration_id,
            self.strike_id,
            self.source_contract_code,
            self.option_type,
            self.expiration,
            self.strike,
            self.multiplier,
        )
        return "RESOLVED" if all(value is not None for value in required) else "UNRESOLVED"


def build_option_contract(metadata: dict) -> OptionContract:
    """Build a canonical contract only from explicit provider metadata."""
    option_type = normalize_option_type(metadata.get("option_type"))
    return OptionContract(
        symbol=str(metadata.get("symbol") or metadata.get("root") or ""),
        root=str(metadata.get("root") or ""),
        exchange=str(metadata.get("exchange") or ""),
        underlying=str(metadata.get("underlying") or ""),
        option_type=option_type,
        expiration=metadata.get("expiration"),
        strike=metadata.get("strike"),
        multiplier=metadata.get("multiplier"),
        currency=metadata.get("currency"),
        settlement_type=metadata.get("settlement_type"),
        source=str(metadata.get("source") or ""),
        source_contract_code=metadata.get("source_contract_code"),
        instrument_id=metadata.get("instrument_id"),
        future_id=metadata.get("future_id"),
        expiration_id=metadata.get("expiration_id"),
        strike_id=metadata.get("strike_id"),
    )


Contract = OptionContract
