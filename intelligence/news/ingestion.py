from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from intelligence.news.normalization import normalize_news


class NewsSourceAdapter:
    """Source-specific transport boundary. It never fabricates missing fields."""

    def __init__(self, source_name: str, fetch: Callable[[], Iterable[dict[str, Any]]]):
        self.source_name = source_name
        self.fetch = fetch

    def collect(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.fetch()]


def ingest(adapter: NewsSourceAdapter, *, detected_at: datetime | None = None):
    current = detected_at or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("DETECTED_AT_MUST_BE_TIMEZONE_AWARE")
    return [
        normalize_news(item, detected_at=current)
        for item in adapter.collect()
    ]
