from datetime import datetime, timezone

from src.news_announcement import (
    NewsItem,
    _category,
    _relevance,
    format_news_announcement,
)


def test_gold_relevant_news_is_classified():
    text = "Federal Reserve interest rate and inflation"
    assert _category(text) == "MONETARY_POLICY"
    assert _relevance(text) == "HIGH"


def test_news_announcement_is_source_only():
    item = NewsItem(
        source="FED_MONETARY",
        external_id="abc",
        headline="Federal Reserve statement",
        summary="details",
        url="https://www.federalreserve.gov/example",
        published_at=datetime(2026, 10, 2, tzinfo=timezone.utc).isoformat(),
        detected_at=datetime(2026, 10, 2, tzinfo=timezone.utc).isoformat(),
        category="MONETARY_POLICY",
        relevance="HIGH",
        rights_status="SOURCE_POLICY_REVIEW",
    )
    text = format_news_announcement([item])
    assert "NEWS ANNOUNCEMENT" in text
    assert item.headline in text
    assert item.url in text
    assert "ยังไม่ใช่ข้อสรุปทิศทางตลาด" in text
    assert "details" not in text
