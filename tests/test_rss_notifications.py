from datetime import datetime, timezone

from intelligence.news.rss import parse_rss
from intelligence.notifications import NotificationPreferences


RSS = '''<?xml version="1.0"?><rss><channel>
<item><title>Fed statement</title><link>https://example.test/fed</link>
<pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate></item>
</channel></rss>'''

def test_rss_parsing_keeps_source_metadata_only():
    rows = parse_rss(RSS, source_name="Example")
    assert rows[0]["source"] == "Example"
    assert rows[0]["url"] == "https://example.test/fed"
    assert rows[0]["published_at"].tzinfo == timezone.utc


def test_notification_preferences_apply_quiet_hours():
    prefs = NotificationPreferences(quiet_hours_start=22, quiet_hours_end=7)
    assert not prefs.allows("MARKET_NEWS", hour=23)
    assert prefs.allows("CRITICAL_NEWS", hour=23)
    assert prefs.allows("MARKET_NEWS", hour=12)