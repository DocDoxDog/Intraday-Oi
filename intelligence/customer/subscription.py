from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

ACTIVE_STATUSES = {"TRIALING", "ACTIVE"}

@dataclass(frozen=True)
class SubscriptionState:
    organization_id: str
    plan_id: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool

    @property
    active(self) -> bool:
        return self.status in ACTIVE_STATUSES

PLAN_FEATURES = {
    "FREE": {"market_overview", "news"},
    "PRO": {"market_overview", "news", "oi", "gex", "positioning", "morning_brief"},
    "ADVANCED": {"market_overview", "news", "oi", "gex", "positioning", "plan", "analysis", "history", "morning_brief"},
    "TEAM": {"market_overview", "news", "oi", "gex", "positioning", "plan", "analysis", "history", "team"},
    "API": {"market_overview", "news", "oi", "gex", "positioning", "api"},
}

def features_for_subscription(state: SubscriptionState) -> frozenset[str]:
    if not state.active:
        return frozenset()
    return frozenset(PLAN_FEATURES.get(state.plan_id, set()))