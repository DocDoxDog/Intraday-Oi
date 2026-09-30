from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from intelligence.news.models import NewsItem, NewsSeverity, NewsStatus


def _require_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name}_REQUIRED")
    return text


def normalize_news(
    raw: dict[str, Any],
    *,
    detected_at: datetime,
    default_language: str = "en",
) -> NewsItem:
    if detected_at.tzinfo is None:
        raise ValueError("DETECTED_AT_MUST_BE_TIMEZONE_AWARE")

    headline = _require_text(raw.get("headline"), "HEADLINE")
    source = _require_text(raw.get("source"), "SOURCE")
    url = _require_text(raw.get("url"), "URL")
    published_raw = raw.get("published_at")
    if not isinstance(published_raw, datetime):
        raise ValueError("PUBLISHED_AT_REQUIRED")
    if published_raw.tzinfo is None:
        raise ValueError("PUBLISHED_AT_MUST_BE_TIMEZONE_AWARE")

    canonical = re.sub(r"\s+", " ", headline).strip().lower()
    news_id = hashlib.sha256(
        f"{source}|{url}|{published_raw.isoformat()}|{canonical}".encode()
    ).hexdigest()[:32]

    severity = NewsSeverity(str(raw.get("severity", NewsSeverity.MEDIUM.value)).upper())
    return NewsItem(
        news_id=news_id,
        headline=headline,
        source=source,
        url=url,
        published_at=published_raw,
        detected_at=detected_at,
        event_time=raw.get("event_time"),
        language=str(raw.get("language") or default_language),
        category=str(raw.get("category") or "UNKNOWN"),
        entities=tuple(sorted({str(x).strip() for x in raw.get("entities", []) if str(x).strip()})),
        assets=tuple(sorted({str(x).strip().upper() for x in raw.get("assets", []) if str(x).strip()})),
        severity=severity,
        status=NewsStatus.PENDING,
        provenance_id=raw.get("provenance_id"),
    )
