from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from intelligence.news.dedupe import cluster_news
from intelligence.news.models import NewsItem
from intelligence.news.normalization import normalize_news
from intelligence.news.providers import fetch_free_news_bundle


def collect_free_news(
    *,
    detected_at: datetime | None = None,
    gdelt_query: str = "(war OR conflict OR missile OR sanctions OR ceasefire OR airstrike)",
    gdelt_timespan: str = "1h",
    gdelt_maxrecords: int = 25,
) -> tuple[list[NewsItem], list[Any]]:
    now = detected_at or datetime.now(timezone.utc)
    raw = fetch_free_news_bundle(
        gdelt_query=gdelt_query,
        gdelt_timespan=gdelt_timespan,
        gdelt_maxrecords=gdelt_maxrecords,
    )

    normalized: list[NewsItem] = []
    for item in raw:
        try:
            normalized.append(normalize_news(item, detected_at=now))
        except (TypeError, ValueError):
            # A malformed item must not contaminate the rest of the feed.
            continue

    clusters = cluster_news(normalized) if normalized else []
    return normalized, clusters


def news_context(items: list[NewsItem], clusters: list[Any]) -> list[dict[str, Any]]:
    """JSON-safe context for the analyst; no article bodies are included."""
    cluster_by_id = {}
    for cluster in clusters:
        for news_id in cluster.news_ids:
            cluster_by_id[news_id] = cluster

    out: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda x: x.published_at, reverse=True):
        cluster = cluster_by_id.get(item.news_id)
        out.append(
            {
                "news_id": item.news_id,
                "headline": item.headline,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at.isoformat(),
                "detected_at": item.detected_at.isoformat(),
                "category": item.category,
                "entities": list(item.entities),
                "assets": list(item.assets),
                "severity": item.severity.value,
                "story_cluster_id": cluster.cluster_id if cluster else None,
                "source_count": cluster.source_count if cluster else 1,
                "official_source": cluster.official_source if cluster else False,
            }
        )
    return out
