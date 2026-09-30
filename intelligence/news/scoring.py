from __future__ import annotations

from intelligence.news.models import NewsImpact, NewsItem, NewsPriority, NewsSeverity


def score_priority(
    item: NewsItem,
    impact: NewsImpact,
    *,
    source_reliability: float,
    novelty: float,
    asset_relevance: float,
    freshness: float,
) -> NewsPriority:
    components = {
        "severity": {
            NewsSeverity.CRITICAL: 1.0,
            NewsSeverity.HIGH: 0.8,
            NewsSeverity.MEDIUM: 0.5,
            NewsSeverity.LOW: 0.2,
            NewsSeverity.IGNORE: 0.0,
        }[item.severity],
        "market_relevance": impact.market_confirmation.score,
        "asset_relevance": max(0.0, min(1.0, asset_relevance)),
        "source_reliability": max(0.0, min(1.0, source_reliability)),
        "novelty": max(0.0, min(1.0, novelty)),
        "market_confirmation": max(0.0, min(1.0, impact.market_confirmation.score)),
        "event_freshness": max(0.0, min(1.0, freshness)),
    }
    score = (
        0.25 * components["severity"]
        + 0.20 * components["market_relevance"]
        + 0.15 * components["asset_relevance"]
        + 0.15 * components["source_reliability"]
        + 0.10 * components["novelty"]
        + 0.10 * components["market_confirmation"]
        + 0.05 * components["event_freshness"]
    )
    return NewsPriority(news_id=item.news_id, score=score, components=components)
