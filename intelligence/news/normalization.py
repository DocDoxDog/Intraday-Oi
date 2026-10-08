from __future__ import annotations
import hashlib,re
from datetime import datetime
from intelligence.news.models import NewsItem,NewsSeverity

def normalize_news(raw:dict, *,detected_at:datetime)->NewsItem:
    headline=str(raw.get("headline") or "").strip(); source=str(raw.get("source") or "").strip(); url=str(raw.get("url") or "").strip(); published=raw.get("published_at")
    if not headline or not source or not url or not isinstance(published,datetime) or published.tzinfo is None: raise ValueError("INVALID_NEWS_ITEM")
    canonical=re.sub(r"\\s+"," ",headline).strip().lower()
    nid=hashlib.sha256(f"{source}|{url}|{published.isoformat()}|{canonical}".encode()).hexdigest()[:32]
    calendar = raw.get("calendar") or {}
    def _calendar_value(key: str) -> str | None:
        value = calendar.get(key)
        if value is None:
            return None
        text = str(value).strip()
        if text in {"", "-", "—", "–", "n/a", "N/A", "NA"}:
            return None
        return text or None

    retrieved_raw = calendar.get("retrieved_at")
    calendar_retrieved_at = None
    if retrieved_raw:
        try:
            calendar_retrieved_at = (
                retrieved_raw
                if isinstance(retrieved_raw, datetime)
                else datetime.fromisoformat(str(retrieved_raw).replace("Z", "+00:00"))
            )
            if calendar_retrieved_at.tzinfo is None:
                calendar_retrieved_at = None
        except (TypeError, ValueError):
            calendar_retrieved_at = None

    return NewsItem(
        news_id=nid,
        headline=headline,
        source=source,
        url=url,
        published_at=published,
        detected_at=detected_at,
        event_time=raw.get("event_time"),
        actual=_calendar_value("actual"),
        forecast=_calendar_value("forecast"),
        previous=_calendar_value("previous"),
        calendar_data_status=str(calendar.get("data_status") or "UNKNOWN"),
        actual_source=calendar.get("actual_source"),
        forecast_source=calendar.get("forecast_source"),
        previous_source=calendar.get("previous_source"),
        calendar_retrieved_at=calendar_retrieved_at,
        language=str(raw.get("language") or "en"),
        category=str(raw.get("category") or "UNKNOWN"),
        entities=tuple(raw.get("entities") or ()),
        assets=tuple(raw.get("assets") or ()),
        severity=NewsSeverity(str(raw.get("severity") or "MEDIUM").upper()),
    )
