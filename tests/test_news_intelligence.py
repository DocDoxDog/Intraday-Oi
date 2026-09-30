from datetime import datetime, timezone, timedelta

import pytest

from intelligence.alert_policy import AlertGate, AlertPolicy
from intelligence.analysis.verifier import verify_output
from intelligence.market_confirmation import confirm_market_reaction
from intelligence.news.asset_mapping import map_assets
from intelligence.news.dedupe import cluster_news, similarity
from intelligence.news.models import NewsItem, NewsSeverity, NewsStatus
from intelligence.news.normalization import normalize_news
from intelligence.news.impact import assess_impact
from intelligence.news.scoring import score_priority


T0 = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def item(headline, source, published):
    return NewsItem(
        news_id=f"{source}-{published.isoformat()}",
        headline=headline,
        source=source,
        url=f"https://{source}.example/story",
        published_at=published,
        detected_at=published + timedelta(minutes=1),
        entities=("FED",),
        assets=("GOLD",),
        severity=NewsSeverity.HIGH,
        status=NewsStatus.PENDING,
    )


def test_normalization_requires_source_timestamps():
    with pytest.raises(ValueError, match="PUBLISHED_AT_REQUIRED"):
        normalize_news({"headline": "CPI", "source": "BLS", "url": "https://bls.example"}, detected_at=T0)

    normalized = normalize_news(
        {
            "headline": "  CPI surprise  ",
            "source": "BLS",
            "url": "https://bls.example/cpi",
            "published_at": T0,
        },
        detected_at=T0 + timedelta(minutes=1),
    )
    assert normalized.headline == "CPI surprise"
    assert normalized.source == "BLS"
    assert normalized.url.startswith("https://")


def test_story_clustering_deduplicates_similar_headlines():
    a = item("Fed holds rates steady, signals caution", "Reuters", T0)
    b = item("Fed holds rates steady and signals caution", "CNBC", T0 + timedelta(minutes=3))
    assert similarity(a, b) > 0.78
    clusters = cluster_news([a, b])
    assert len(clusters) == 1
    assert clusters[0].source_count == 2


def test_asset_mapping_does_not_assert_direction():
    mappings = map_assets("OPEC announces production cut")
    assert {m.asset for m in mappings} == {"USOIL", "UKOIL"}
    assert all(m.direction == "UNCERTAIN" for m in mappings)


def test_impact_and_priority_are_transparent():
    item_a = item("Fed decision", "Federal Reserve", T0)
    cluster = cluster_news([item_a])[0]
    confirmation = confirm_market_reaction(
        price_reaction=0.8,
        volatility_reaction=0.5,
        oi_change=0.2,
        gex_change=0.1,
        dex_change=None,
        market_state_changed=True,
    )
    impact = assess_impact(item_a, cluster, confirmation)
    priority = score_priority(
        item_a,
        impact,
        source_reliability=1.0,
        novelty=0.9,
        asset_relevance=1.0,
        freshness=1.0,
    )
    assert 0.0 <= priority.score <= 1.0
    assert set(priority.components) == {
        "severity", "market_relevance", "asset_relevance",
        "source_reliability", "novelty", "market_confirmation", "event_freshness"
    }


def test_alert_gate_enforces_same_story_and_budget():
    gate = AlertGate(AlertPolicy(max_alerts_per_hour=1, max_news_alerts_per_day=2))
    allowed, reason = gate.allow(severity="HIGH", story_cluster_id="s1", now=T0)
    assert (allowed, reason) == (True, "ALLOWED")
    allowed, reason = gate.allow(severity="HIGH", story_cluster_id="s2", now=T0 + timedelta(minutes=1))
    assert (allowed, reason) == (False, "HOURLY_BUDGET")

    gate = AlertGate(AlertPolicy())
    assert gate.allow(severity="HIGH", story_cluster_id="s1", now=T0)[0] is True
    assert gate.allow(severity="HIGH", story_cluster_id="s1", now=T0 + timedelta(minutes=1)) == (
        False, "SAME_STORY_COOLDOWN"
    )


def test_ai_verifier_accepts_zero_metadata_values():
    result = verify_output(
        "Price 0.0",
        allowed_numbers={0.0},
        source_urls=set(),
        required_metadata={
            "as_of": "2026-10-01T00:00:00+00:00",
            "data_age": 0,
            "data_quality": 0,
            "dataset_version": "v1",
            "calculation_version": "c1",
            "assumptions": ("x",),
        },
    )
    assert result.ok is True
