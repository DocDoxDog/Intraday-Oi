from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from enum import Enum

class RightsStatus(str, Enum):
    APPROVED = "APPROVED"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    BLOCKED = "BLOCKED"

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
    effective_to: date | None = None

    def allows_customer_distribution(self, as_of: date) -> bool:
        if self.effective_from > as_of:
            return False
        if self.effective_to is not None and as_of >= self.effective_to:
            return False
        return self.rights_status == RightsStatus.APPROVED and self.commercial_use and self.redistribution

DEFAULT_SOURCE_POLICIES = (
    NewsSourcePolicy("Reuters", "licensed_feed", RightsStatus.LICENSE_REQUIRED, False, False, True, None, date(2026, 1, 1)),
    NewsSourcePolicy("Bloomberg", "licensed_data", RightsStatus.LICENSE_REQUIRED, False, False, True, None, date(2026, 1, 1)),
    NewsSourcePolicy("Federal Reserve", "official_public", RightsStatus.LEGAL_REVIEW_REQUIRED, False, False, True, None, date(2026, 1, 1)),
    NewsSourcePolicy("EIA", "official_api", RightsStatus.LEGAL_REVIEW_REQUIRED, False, False, True, None, date(2026, 1, 1)),
)