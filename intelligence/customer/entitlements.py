from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Entitlement:
    organization_id: str
    feature: str
    enabled: bool
    effective_from: datetime
    effective_to: datetime | None = None

    def active(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        if current < self.effective_from:
            return False
        return self.effective_to is None or current < self.effective_to


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


def check_entitlement(
    entitlements: tuple[Entitlement, ...],
    *,
    organization_id: str,
    feature: str,
    now: datetime | None = None,
) -> AccessDecision:
    for item in entitlements:
        if item.organization_id == organization_id and item.feature == feature:
            return AccessDecision(
                allowed=item.enabled and item.active(now),
                reason="ENTITLEMENT_ACTIVE" if item.enabled and item.active(now) else "ENTITLEMENT_DISABLED",
            )
    return AccessDecision(False, "ENTITLEMENT_NOT_FOUND")
