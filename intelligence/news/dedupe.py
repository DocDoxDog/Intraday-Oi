from __future__ import annotations

from difflib import SequenceMatcher

from intelligence.news.models import NewsItem, StoryCluster


def similarity(a: NewsItem, b: NewsItem) -> float:
    headline = SequenceMatcher(
        None, a.headline.lower(), b.headline.lower(), autojunk=False
    ).ratio()
    entities_a = set(a.entities)
    entities_b = set(b.entities)
    entity_score = (
        len(entities_a & entities_b) / len(entities_a | entities_b)
        if entities_a or entities_b else 0.0
    )
    time_delta = abs((a.published_at - b.published_at).total_seconds())
    time_score = max(0.0, 1.0 - time_delta / 3600.0)
    return 0.60 * headline + 0.25 * entity_score + 0.15 * time_score


def cluster_news(items: list[NewsItem], threshold: float = 0.78) -> list[StoryCluster]:
    clusters: list[list[NewsItem]] = []
    for item in sorted(items, key=lambda x: x.published_at):
        target = None
        best = 0.0
        for idx, group in enumerate(clusters):
            score = max(similarity(item, other) for other in group)
            if score >= threshold and score > best:
                target = idx
                best = score
        if target is None:
            clusters.append([item])
        else:
            clusters[target].append(item)

    result: list[StoryCluster] = []
    for idx, group in enumerate(clusters):
        ordered = sorted(group, key=lambda x: x.published_at)
        official = any(
            item.source.lower() in {
                "federal reserve", "bls", "bea", "eia", "cftc", "cme",
                "ecb", "boj", "opec"
            }
            for item in group
        )
        result.append(
            StoryCluster(
                cluster_id=f"story-{idx+1:04d}",
                canonical_headline=ordered[0].headline,
                news_ids=tuple(x.news_id for x in group),
                source_count=len({x.source for x in group}),
                first_published_at=ordered[0].published_at,
                last_published_at=ordered[-1].published_at,
                official_source=official,
            )
        )
    return result
