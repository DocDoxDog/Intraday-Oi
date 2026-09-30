from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

class RightsState(str, Enum):
    APPROVED = "APPROVED"
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    DENIED = "DENIED"

def _enum_value(value: RightsState | str) -> str:
    return value.value if isinstance(value, RightsState) else str(value)

@dataclass(frozen=True)
class SourceRights:
    source_id: str
    state: RightsState | str
    raw_storage: bool = False
    customer_display: bool = False
    api_distribution: bool = False
    alert_distribution: bool = False
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    agreement_ref: str | None = None

    def active(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
        if self.effective_from and self.effective_from > current:
            return False
        if self.effective_to and current >= self.effective_to:
            return False
        return True

def can_distribute(rights: SourceRights, *, surface: str, now: datetime | None = None) -> bool:
    if not rights.active(now) or _enum_value(rights.state) != RightsState.APPROVED.value:
        return False
    if surface == "CUSTOMER_DISPLAY":
        return rights.customer_display
    if surface == "API":
        return rights.api_distribution
    if surface == "ALERT":
        return rights.alert_distribution
    if surface == "RAW_STORAGE":
        return rights.raw_storage
    raise ValueError(f"UNKNOWN_SURFACE:{surface}")
