from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class RightsStatus(str, Enum):
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    OPEN_LICENSE = "OPEN_LICENSE"
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    PROHIBITED = "PROHIBITED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NewsSourcePolicy:
    source: str
    access_method: str
    rights_status: RightsStatus
    commercial_use: bool
    redistribution: bool
    attribution_required: bool
    retention_days: int | None
    effective_from: date
    effective_until: date | None = None

    def allows_customer_distribution(self, on_date: date) -> bool:
        if on_date < self.effective_from:
            return False
        if self.effective_until is not None and on_date > self.effective_until:
            return False
        return (
            self.rights_status in {RightsStatus.PUBLIC_DOMAIN, RightsStatus.OPEN_LICENSE}
            and self.commercial_use
            and self.redistribution
        )


DEFAULT_SOURCE_POLICIES = (
    NewsSourcePolicy(
        source="Reuters", access_method="licensed_feed",
        rights_status=RightsStatus.LICENSE_REQUIRED, commercial_use=False,
        redistribution=False, attribution_required=True, retention_days=None,
        effective_from=date(2000, 1, 1),
    ),
    NewsSourcePolicy(
        source="Forex Factory", access_method="public_calendar",
        rights_status=RightsStatus.LEGAL_REVIEW_REQUIRED, commercial_use=False,
        redistribution=False, attribution_required=True, retention_days=30,
        effective_from=date(2000, 1, 1),
    ),
)
