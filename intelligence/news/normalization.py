from __future__ import annotations
import hashlib,re
from datetime import datetime
from intelligence.news.models import NewsItem,NewsSeverity

def normalize_news(raw:dict, *,detected_at:datetime)->NewsItem:
    headline=str(raw.get("headline") or "").strip(); source=str(raw.get("source") or "").strip(); url=str(raw.get("url") or "").strip(); published=raw.get("published_at")
    if not headline or not source or not url or not isinstance(published,datetime) or published.tzinfo is None: raise ValueError("INVALID_NEWS_ITEM")
    canonical=re.sub(r"\\s+"," ",headline).strip().lower()
    nid=hashlib.sha256(f"{source}|{url}|{published.isoformat()}|{canonical}".encode()).hexdigest()[:32]
    return NewsItem(news_id=nid,headline=headline,source=source,url=url,published_at=published,detected_at=detected_at,event_time=raw.get("event_time"),language=str(raw.get("language") or "en"),category=str(raw.get("category") or "UNKNOWN"),entities=tuple(raw.get("entities") or ()),assets=tuple(raw.get("assets") or ()),severity=NewsSeverity(str(raw.get("severity") or "MEDIUM").upper()))
