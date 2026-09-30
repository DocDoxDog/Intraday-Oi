from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree as ET

from intelligence.news.ingestion import NewsSourceAdapter


def parse_rss(xml_payload: str, *, source_name: str) -> list[dict]:
    root = ET.fromstring(xml_payload)
    items = []
    for item in root.findall('.//item'):
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        published = (item.findtext('pubDate') or '').strip()
        if not title or not link or not published:
            continue
        from email.utils import parsedate_to_datetime
        published_at = parsedate_to_datetime(published)
        items.append({
            'headline': title, 'source': source_name, 'url': link,
            'published_at': published_at,
        })
    return items


class RssNewsSource(NewsSourceAdapter):
    pass