from __future__ import annotations
from datetime import datetime,timezone
from intelligence.news.providers import fetch_free_news_bundle
from intelligence.news.normalization import normalize_news
from intelligence.news.dedupe import cluster_news

def collect_free_news(*,detected_at:datetime|None=None)->tuple[list, list]:
    now=detected_at or datetime.now(timezone.utc); raw=fetch_free_news_bundle(); items=[]
    cutoff = now.astimezone(timezone.utc).timestamp() - 72 * 3600
    future_limit = now.astimezone(timezone.utc).timestamp() + 5 * 60
    for row in raw:
        try:
            item = normalize_news(row, detected_at=now)
            ts = item.published_at.astimezone(timezone.utc).timestamp()
            if cutoff <= ts <= future_limit:
                items.append(item)
        except (TypeError,ValueError): continue
    return items,cluster_news(items) if items else []
