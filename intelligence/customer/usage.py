from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class UsageEvent:
    organization_id: str
    endpoint: str
    occurred_at: datetime
    status_code: int
    latency_ms: int
    units: int = 1
    api_key_id: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("OCCURRED_AT_MUST_BE_TIMEZONE_AWARE")
        if self.units < 0:
            raise ValueError("UNITS_MUST_BE_NON_NEGATIVE")
        if self.latency_ms < 0:
            raise ValueError("LATENCY_MUST_BE_NON_NEGATIVE")

    @classmethod
    def now(cls, *, organization_id: str, endpoint: str, status_code: int, latency_ms: int, units: int = 1, api_key_id: str | None = None):
        return cls(
            organization_id=organization_id,
            endpoint=endpoint,
            occurred_at=datetime.now(timezone.utc),
            status_code=status_code,
            latency_ms=latency_ms,
            units=units,
            api_key_id=api_key_id,
        )
