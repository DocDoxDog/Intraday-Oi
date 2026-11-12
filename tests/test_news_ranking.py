from datetime import datetime, timezone

from intelligence.news.ranking import build_news_intelligence, rank_news


NOW = datetime(2026, 11, 13, 1, 0, tzinfo=timezone.utc)


def test_macro_surprise_gets_ranked_and_explained():
    rows = [{
        "source": "BLS_CPI",
        "external_id": "cpi-1",
        "headline": "US CPI higher than expected",
        "url": "https://www.bls.gov/example",
        "published_at": "2026-11-13T00:30:00+00:00",
        "detected_at": NOW.isoformat(),
        "category": "INFLATION",
        "severity": "HIGH",
        "actual": "4.2%",
        "forecast": "3.9%",
        "previous": "3.8%",
        "market_channels": ["INFLATION", "RATES", "USD"],
        "rights_status": "SOURCE_POLICY_REVIEW",
    }]
    ranked = rank_news(rows, detected_at=NOW)
    assert ranked[0]["impact_tier"] in {"HIGH", "CRITICAL"}
    assert ranked[0]["surprise"]["direction"] == "ABOVE_FORECAST"
    assert ranked[0]["gold_bias"] == "POTENTIALLY_NEGATIVE"
    assert "Actual 4.2% vs Forecast 3.9%" in ranked[0]["why_it_matters"]


def test_cross_source_confirmation_is_detected():
    rows = [
        {
            "source": "BLS_CPI",
            "external_id": "cpi-a",
            "headline": "US CPI rises more than expected",
            "url": "https://www.bls.gov/example-a",
            "published_at": "2026-11-13T00:30:00+00:00",
            "category": "INFLATION",
            "severity": "HIGH",
        },
        {
            "source": "GDELT",
            "external_id": "cpi-b",
            "headline": "US CPI rises more than expected",
            "url": "https://example.com/cpi-b",
            "published_at": "2026-11-13T00:31:00+00:00",
            "category": "MACRO",
            "severity": "MEDIUM",
        },
    ]
    ranked = rank_news(rows, detected_at=NOW)
    assert ranked[0]["cross_source_count"] == 2
    assert ranked[0]["cross_source_confirmed"] is True


def test_news_intelligence_returns_primary_stories_only_once():
    rows = [
        {
            "source": "GDELT",
            "external_id": "war-a",
            "headline": "Conflict escalates in region",
            "url": "https://example.com/a",
            "published_at": "2026-11-13T00:20:00+00:00",
            "category": "GEOPOLITICAL",
            "severity": "HIGH",
        },
        {
            "source": "GDELT",
            "external_id": "war-b",
            "headline": "Conflict escalates in region",
            "url": "https://example.com/b",
            "published_at": "2026-11-13T00:21:00+00:00",
            "category": "GEOPOLITICAL",
            "severity": "MEDIUM",
        },
    ]
    intelligence = build_news_intelligence(rows, detected_at=NOW)
    assert len(intelligence["primary_stories"]) == 1
    assert intelligence["primary_stories"][0]["cross_source_count"] == 1
    assert intelligence["primary_stories"][0]["story_primary"] is True
