from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

def _event_status(actual: str | None, event_time: datetime | None, detected_at: datetime) -> str:
    if actual:
        return "RELEASED"
    if event_time is not None:
        event_utc = event_time.astimezone(timezone.utc)
        detected_utc = detected_at.astimezone(timezone.utc)
        return "UPCOMING" if event_utc > detected_utc else "UNKNOWN"
    return "SCHEDULED"


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
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    calendar_data_status: str = "UNKNOWN"
    actual_source: str | None = None
    forecast_source: str | None = None
    previous_source: str | None = None
    calendar_retrieved_at: datetime | None = None
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
        event_status = _event_status(self.actual, self.event_time, self.detected_at)
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
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "actual": self.actual,
            "forecast": self.forecast,
            "previous": self.previous,
            "event_status": event_status,
            "calendar_data_status": self.calendar_data_status,
            "actual_source": self.actual_source,
            "forecast_source": self.forecast_source,
            "previous_source": self.previous_source,
            "calendar_retrieved_at": self.calendar_retrieved_at.isoformat() if self.calendar_retrieved_at else None,
            "category": self.category,
            "relevance": relevance,
            "rights_status": "SOURCE_POLICY_REVIEW",
            "market_channels": sorted(set(channels)),
            "freshness": freshness,
        }
