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
    assert "source announcement เท่านั้น" in text
    assert "details" not in text


def test_xml_rows_handles_leading_bom_and_whitespace():
    from src.news_announcement import _xml_rows
    xml = "\ufeff  \n<rss><channel><item><title>Fed</title><link>https://example.com/fed</link></item></channel></rss>"
    rows = list(_xml_rows(xml))
    assert rows[0]["title"] == "Fed"
    assert rows[0]["link"] == "https://example.com/fed"


def test_collect_news_keeps_valid_feeds_when_one_source_is_broken(monkeypatch):
    from src.news_announcement import collect_news
    good = "<rss><channel><item><title>Federal Reserve interest rate decision</title><link>https://example.com/1</link><pubDate>Thu, 02 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>"

    class Response:
        def __init__(self, body):
            self.text = body
            self.status_code = 200
        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        if url.endswith("press_monetary.xml"):
            return Response("<html>blocked</html>")
        return Response(good)

    monkeypatch.setattr("src.news_announcement.requests.get", fake_get)
    items = collect_news(
        detected_at=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
        max_items_per_source=1,
    )
    assert items
    assert any(item.source != "FED_MONETARY" for item in items)
