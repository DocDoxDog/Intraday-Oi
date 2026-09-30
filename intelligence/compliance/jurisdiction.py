from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RegulatoryProfile:
    jurisdiction: str
    customer_type: str
    feature: str
    enabled: bool
    legal_review_status: str
    effective_from: datetime
    effective_to: datetime | None = None
    required_disclosures: tuple[str, ...] = ()

    def active(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
        return self.effective_from <= current and (
            self.effective_to is None or current < self.effective_to
        )


def feature_allowed(
    profiles: tuple[RegulatoryProfile, ...],
    *,
    jurisdiction: str,
    customer_type: str,
    feature: str,
    now: datetime | None = None,
) -> tuple[bool, str]:
    active = [
        p for p in profiles
        if p.jurisdiction.upper() == jurisdiction.upper()
        and p.customer_type.upper() == customer_type.upper()
        and p.feature == feature
        and p.active(now)
    ]
    if not active:
        return False, "REGULATORY_PROFILE_NOT_FOUND"
    profile = active[-1]
    if profile.legal_review_status != "APPROVED":
        return False, profile.legal_review_status
    return profile.enabled, "REGULATORY_FEATURE_ENABLED" if profile.enabled else "REGULATORY_FEATURE_DISABLED"
