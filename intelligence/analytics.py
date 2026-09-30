from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


@dataclass(frozen=True)
class ProductEvent:
    event_name: str
    channel: str
    occurred_at: datetime
    organization_id: str | None = None
    user_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("OCCURRED_AT_MUST_BE_TIMEZONE_AWARE")


def product_event(
    event_name: str,
    channel: str,
    *,
    organization_id: str | None = None,
    user_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> ProductEvent:
    return ProductEvent(
        event_name=event_name,
        channel=channel,
        occurred_at=datetime.now(timezone.utc),
        organization_id=organization_id,
        user_id=user_id,
        metadata=metadata or {},
    )
