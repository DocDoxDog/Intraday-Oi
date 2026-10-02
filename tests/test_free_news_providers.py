from datetime import datetime, timezone

from intelligence.news.free_feed import collect_free_news, news_context
from intelligence.news.providers import fetch_forex_factory_calendar, fetch_gdelt


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_gdelt_provider_normalizes_article_metadata(monkeypatch):
    monkeypatch.setattr(
        "intelligence.news.providers._get",
        lambda *args, **kwargs: FakeResponse(
            {
                "articles": [
                    {
                        "title": "Missile strike reported after overnight escalation",
                        "url": "https://example.test/story",
                        "seendate": "20261002T120000Z",
                        "domain": "example.test",
                        "language": "English",
                    }
                ]
            }
        ),
    )
    rows = fetch_gdelt(maxrecords=5)
    assert len(rows) == 1
    assert rows[0]["category"] == "GEOPOLITICAL"
    assert rows[0]["assets"] == ("GOLD", "USD", "USOIL", "UKOIL")
    assert rows[0]["published_at"].tzinfo == timezone.utc


def test_forex_factory_provider_maps_calendar_fields(monkeypatch):
    monkeypatch.setattr(
        "intelligence.news.providers._get",
        lambda *args, **kwargs: FakeResponse(
            [
                {
                    "title": "CPI y/y",
                    "country": "USD",
                    "date": "2026-10-02T08:30:00-04:00",
                    "impact": "High",
                    "forecast": "3.4%",
                    "previous": "3.5%",
                }
            ]
        ),
    )
    rows = fetch_forex_factory_calendar()
    assert rows[0]["headline"] == "USD — CPI y/y"
    assert rows[0]["severity"] == "HIGH"
    assert rows[0]["calendar"]["forecast"] == "3.4%"
    assert rows[0]["published_at"].tzinfo == timezone.utc


def test_free_bundle_isolates_provider_failure(monkeypatch):
    from intelligence.news import providers

    def fail_gdelt(*args, **kwargs):
        raise providers.requests.RequestException("GDELT unavailable")

    monkeypatch.setattr(providers, "fetch_gdelt", fail_gdelt)
    monkeypatch.setattr(
        providers,
        "fetch_forex_factory_calendar",
        lambda: [
            {
                "headline": "USD — FOMC Member Speaks",
                "source": "Forex Factory",
                "url": "https://www.forexfactory.com/calendar/",
                "published_at": datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
                "severity": "LOW",
                "assets": ("GOLD",),
            }
        ],
    )
    rows = providers.fetch_free_news_bundle()
    assert len(rows) == 1
    assert rows[0]["source"] == "Forex Factory"


def test_collect_free_news_produces_json_safe_context(monkeypatch):
    monkeypatch.setattr(
        "intelligence.news.free_feed.fetch_free_news_bundle",
        lambda **kwargs: [
            {
                "headline": "Conflict risk rises near shipping route",
                "source": "GDELT",
                "url": "https://example.test/a",
                "published_at": datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
                "category": "GEOPOLITICAL",
                "assets": ("GOLD", "USOIL"),
                "severity": "HIGH",
            }
        ],
    )
    items, clusters = collect_free_news(
        detected_at=datetime(2026, 10, 2, 12, 1, tzinfo=timezone.utc)
    )
    context = news_context(items, clusters)
    assert len(items) == 1
    assert len(clusters) == 1
    assert context[0]["category"] == "GEOPOLITICAL"
    assert context[0]["published_at"].endswith("+00:00")
    assert context[0]["source_count"] == 1
    assert "body" not in context[0]
