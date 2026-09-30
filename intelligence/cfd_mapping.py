from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CfdMapping:
    broker: str
    cfd_symbol: str
    canonical_reference: str
    mapping_version: str
    effective_from: datetime
    effective_to: datetime | None = None

    def active_at(self, when: datetime) -> bool:
        if when.tzinfo is None or self.effective_from.tzinfo is None:
            raise ValueError("MAPPING_TIMES_MUST_BE_TIMEZONE_AWARE")
        return self.effective_from <= when and (
            self.effective_to is None or when < self.effective_to
        )


