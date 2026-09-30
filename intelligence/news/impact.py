from __future__ import annotations

from intelligence.news.models import (
    ImpactDirection,
    MarketConfirmation,
    NewsImpact,
    NewsItem,
    NewsSeverity,
    StoryCluster,
)


_SEVERITY_SCORE = {
    NewsSeverity.CRITICAL: 1.0,
    NewsSeverity.HIGH: 0.8,
    NewsSeverity.MEDIUM: 0.5,
    NewsSeverity.LOW: 0.2,
    NewsSeverity.IGNORE: 0.0,
}


def assess_impact(
    item: NewsItem,
    cluster: StoryCluster,
    confirmation: MarketConfirmation,
    *,
    model_version: str = "news-impact-v1",
) -> NewsImpact:
    base = _SEVERITY_SCORE[item.severity]
    confirmation_score = confirmation.score
    confidence = min(
        1.0,
        0.55 * base
        + 0.25 * confirmation_score
        + 0.10 * min(cluster.source_count / 3.0, 1.0)
        + 0.10 * float(cluster.official_source),
    )
    evidence = list(confirmation.evidence)
    evidence.append(f"severity={item.severity.value}")
    evidence.append(f"source_count={cluster.source_count}")
    return NewsImpact(
        news_id=item.news_id,
        story_cluster_id=cluster.cluster_id,
        severity=item.severity,
        confidence=confidence,
        assets=item.assets,
        direction=ImpactDirection.UNCERTAIN,
        horizon="UNKNOWN",
        impact_reason=tuple(evidence),
        source_count=cluster.source_count,
        official_source=cluster.official_source,
        market_confirmation=confirmation,
        model_version=model_version,
    )
