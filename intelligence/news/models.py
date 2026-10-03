from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

class NewsSeverity(str, Enum):
    CRITICAL="CRITICAL"; HIGH="HIGH"; MEDIUM="MEDIUM"; LOW="LOW"; IGNORE="IGNORE"

@dataclass(frozen=True)
class NewsItem:
    news_id: str
    headline: str
    source: str
    url: str
    published_at: datetime
    detected_at: datetime
    event_time: datetime | None = None
    language: str = "en"
    category: str = "UNKNOWN"
    entities: tuple[str,...] = ()
    assets: tuple[str,...] = ()
    severity: NewsSeverity = NewsSeverity.MEDIUM
    def as_legacy_dict(self) -> dict:
        now = self.detected_at.astimezone(timezone.utc)
        age_hours = max(0.0, (now - self.published_at.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if age_hours <= 6:
            freshness = "FRESH"
        elif age_hours <= 24:
            freshness = "RECENT"
        elif age_hours <= 72:
            freshness = "AGING"
        else:
            freshness = "STALE"
        if self.severity in {NewsSeverity.CRITICAL, NewsSeverity.HIGH}:
            relevance = "HIGH"
        elif self.severity == NewsSeverity.MEDIUM:
            relevance = "MEDIUM"
        else:
            relevance = "LOW"
        text_lower = self.headline.lower()
        channels = []
        if any(x in text_lower for x in ("nonfarm payroll", "payroll", "employment situation", "unemployment", "jobs report")):
            channels.append("LABOR")
        if self.category == "GEOPOLITICAL":
            channels.append("RISK_SENTIMENT")
        elif self.category == "MACRO":
            channels.append("MACRO")
        return {
            "source": self.source,
            "external_id": self.news_id,
            "headline": self.headline,
            "summary": None,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "detected_at": self.detected_at.isoformat(),
            "category": self.category,
            "relevance": relevance,
            "rights_status": "SOURCE_POLICY_REVIEW",
            "market_channels": sorted(set(channels)),
            "freshness": freshness,
        }
