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


def test_free_calendar_values_survive_normalization():
    from datetime import datetime, timezone
    from intelligence.news.normalization import normalize_news

    detected = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)
    event_time = datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc)
    item = normalize_news(
        {
            "headline": "USD — FOMC Meeting Minutes",
            "source": "Forex Factory",
            "url": "https://www.forexfactory.com/calendar/",
            "published_at": event_time,
            "event_time": event_time,
            "category": "MACRO",
            "severity": "HIGH",
            "calendar": {"actual": "", "forecast": "-", "previous": "4.50%"},
        },
        detected_at=detected,
    )
    row = item.as_legacy_dict()
    assert row["actual"] is None
    assert row["forecast"] == "-"
    assert row["previous"] == "4.50%"
    assert row["event_time"] == event_time.isoformat()


def test_news_announcement_renders_actual_forecast_previous_without_invention():
    item = {
        "category": "MACRO",
        "headline": "USD — FOMC Meeting Minutes",
        "source": "Forex Factory",
        "published_at": "2026-10-08T05:00:00+00:00",
        "event_time": "2026-10-08T05:00:00+00:00",
        "detected_at": "2026-10-08T04:00:00+00:00",
        "actual": None,
        "forecast": "-",
        "previous": "4.50%",
        "url": "https://www.forexfactory.com/calendar/",
    }
    text = format_news_announcement([item])
    assert "สถานะ: UPCOMING" in text
    assert "Actual: —" in text
    assert "Forecast: -" in text
    assert "Previous: 4.50%" in text


def test_forex_factory_provider_keeps_actual_forecast_previous(monkeypatch):
    from intelligence.news import providers

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return [{
                "title": "FOMC Meeting Minutes",
                "country": "USD",
                "date": "2026-10-08T05:00:00+00:00",
                "impact": "High",
                "actual": "4.00%",
                "forecast": "4.25%",
                "previous": "4.50%",
            }]

    monkeypatch.setattr(providers, "_get", lambda *args, **kwargs: Response())
    rows = providers.fetch_forex_factory_calendar()
    assert rows[0]["calendar"]["actual"] == "4.00%"
    assert rows[0]["calendar"]["forecast"] == "4.25%"
    assert rows[0]["calendar"]["previous"] == "4.50%"


def test_forex_factory_html_enriches_released_actual_without_api_key(monkeypatch):
    from intelligence.news import providers

    class JsonResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return [{
                "title": "Crude Oil Inventories",
                "country": "USD",
                "date": "2026-10-07T18:00:00+00:00",
                "impact": "High",
                "actual": "",
                "forecast": "1.9M",
                "previous": "0.9M",
            }]

    html = """
    <table class="calendar__table">
      <tr class="calendar__row calendar_row">
        <td class="calendar__cell calendar__date date">Wed Oct 7</td>
        <td class="calendar__cell calendar__time time">7:00pm</td>
        <td class="calendar__cell calendar__currency currency">USD</td>
        <td class="calendar__cell calendar__impact impact"><span title="High Impact Expected"></span></td>
        <td class="calendar__cell calendar__event event">Crude Oil Inventories</td>
        <td class="calendar__cell calendar__actual actual"><span>-3.2M</span></td>
        <td class="calendar__cell calendar__forecast forecast"><span class="calendar-forecast">1.9M</span></td>
        <td class="calendar__cell calendar__previous previous"><span class="calendar-previous">0.9M</span></td>
      </tr>
    </table>
    """

    class Response:
        def __init__(self, payload=None, body=""):
            self._payload = payload
            self.text = body
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if url.endswith("ff_calendar_thisweek.json"):
            return Response(JsonResponse().json())
        return Response(body=html)

    monkeypatch.setattr(providers, "_get", fake_get)
    rows = providers.fetch_forex_factory_calendar()
    assert rows[0]["calendar"]["actual"] == "-3.2M"
    assert rows[0]["calendar"]["actual_source"] == "forexfactory_html"
    assert rows[0]["calendar"]["data_status"] == "HTML_ENRICHED"


def test_missing_calendar_placeholders_are_unknown_not_literal_dash():
    from intelligence.news.normalization import normalize_news

    detected = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)
    event_time = datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc)
    item = normalize_news(
        {
            "headline": "USD — FOMC Meeting Minutes",
            "source": "Forex Factory",
            "url": "https://www.forexfactory.com/calendar/",
            "published_at": event_time,
            "event_time": event_time,
            "category": "MACRO",
            "severity": "HIGH",
            "calendar": {
                "actual": "",
                "forecast": "-",
                "previous": "4.50%",
                "data_status": "HTML_ENRICHED",
                "actual_source": None,
                "forecast_source": "forexfactory_json",
                "previous_source": "forexfactory_html",
            },
        },
        detected_at=detected,
    )
    row = item.as_legacy_dict()
    assert row["actual"] is None
    assert row["forecast"] is None
    assert row["previous"] == "4.50%"
    assert row["event_status"] == "UPCOMING"
    assert row["calendar_data_status"] == "HTML_ENRICHED"
    assert row["previous_source"] == "forexfactory_html"
