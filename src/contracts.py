"""Canonical GC/OG contract model.

This module normalizes identifiers without inventing missing exchange metadata.
Unknown fields remain None and must be resolved from authoritative reference data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class Contract:
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

    @property
    def is_option(self) -> bool:
        return self.option_type is not None

    @property
    def canonical_key(self) -> str:
        expiry = self.expiration.isoformat() if self.expiration else "UNKNOWN_EXPIRY"
        strike = f"{self.strike:g}" if self.strike is not None else "UNKNOWN_STRIKE"
        side = self.option_type.value if self.option_type else "FUTURE"
        return f"{self.exchange}:{self.root}:{self.underlying}:{expiry}:{strike}:{side}"


def normalize_option_type(value: str | None) -> OptionType | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized in {"C", "CALL"}:
        return OptionType.CALL
    if normalized in {"P", "PUT"}:
        return OptionType.PUT
    raise ValueError(f"UNKNOWN_OPTION_TYPE:{value}")
