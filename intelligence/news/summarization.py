from __future__ import annotations

from intelligence.news.models import StoryCluster


def build_safe_summary_context(cluster: StoryCluster, headlines: list[str]) -> dict:
    """Build structured LLM input. It does not call an LLM or add factual claims."""
    return {
        "cluster_id": cluster.cluster_id,
        "source_count": cluster.source_count,
        "official_source": cluster.official_source,
        "headlines": list(headlines),
        "instructions": (
            "Summarize only supplied headlines and metadata. "
            "Do not invent numbers, sources, dates, causality or market outcomes."
        ),
    }
