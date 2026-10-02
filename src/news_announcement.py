"""Deterministic macro/news announcement ingestion for the GOLD OI bot.

This phase intentionally separates:
- source collection
- relevance filtering
- deduplication
- customer announcement

LLM interpretation is not performed here. Headlines and timestamps stay tied
to the source item so later analyst claims can cite the exact evidence.
"""

from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import requests


@dataclass(frozen=True)
class NewsSource:
    key: str
    url: str
    kind: str
    rights_status: str = "SOURCE_POLICY_REVIEW"


@dataclass(frozen=True)
class NewsItem:
    source: str
    external_id: str
    headline: str
    summary: str | None
    url: str
    published_at: str | None
    detected_at: str
    category: str
    relevance: str
    rights_status: str

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "external_id": self.external_id,
            "headline": self.headline,
            "summary": self.summary,
            "url": self.url,
            "published_at": self.published_at,
            "detected_at": self.detected_at,
            "category": self.category,
            "relevance": self.relevance,
            "rights_status": self.rights_status,
        }


NEWS_SOURCES = (
    NewsSource("FED_MONETARY", "https://www.federalreserve.gov/feeds/press_monetary.xml", "rss"),
    NewsSource("BLS_EMPLOYMENT", "https://www.bls.gov/feed/empsit.rss", "rss"),
    NewsSource("BLS_CPI", "https://www.bls.gov/feed/cpi.rss", "rss"),
    NewsSource("BLS_PPI", "https://www.bls.gov/feed/ppi.rss", "rss"),
    NewsSource("BLS_JOLTS", "https://www.bls.gov/feed/jolts.rss", "rss"),
    NewsSource("BEA_RELEASES", "https://apps.bea.gov/rss/rss.xml", "rss"),
)

_CATEGORY_KEYWORDS = {
    "MONETARY_POLICY": (
        "federal reserve", "fomc", "fed ", "interest rate", "policy rate",
        "monetary policy", "rate decision", "rate cut", "rate hike",
    ),
    "INFLATION": (
        "consumer price index", "cpi", "producer price index", "ppi",
        "inflation", "prices", "personal consumption expenditures", "pce",
    ),
    "LABOR": (
        "employment situation", "nonfarm payroll", "payroll", "unemployment",
        "job openings", "jolts", "wages", "labor market",
    ),
    "GROWTH": (
        "gross domestic product", "gdp", "personal income", "personal outlays",
        "consumer spending", "economic growth",
    ),
    "RATES_LIQUIDITY": (
        "treasury", "yield", "liquidity", "balance sheet", "policy rates",
    ),
}

_GOLD_RELEVANCE_KEYWORDS = (
    "gold", "dollar", "dxy", "yield", "treasury", "real yield",
    "federal reserve", "fomc", "interest rate", "inflation", "cpi", "ppi",
    "pce", "employment", "payroll", "unemployment", "jolts", "gdp",
    "liquidity", "central bank", "geopolit", "recession",
)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _parse_time(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _category(text: str) -> str:
    haystack = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return "OTHER"


def _relevance(text: str) -> str:
    haystack = text.lower()
    hits = sum(1 for keyword in _GOLD_RELEVANCE_KEYWORDS if keyword in haystack)
    if hits >= 2:
        return "HIGH"
    if hits == 1:
        return "MEDIUM"
    return "LOW"


def _xml_rows(xml_text: str) -> Iterable[dict]:
    cleaned = (xml_text or "").lstrip("\ufeff\x00 \t\r\n")
    # Public feeds occasionally contain XML-invalid control bytes. Remove only
    # characters forbidden by XML 1.0; never alter printable feed content.
    cleaned = "".join(
        ch for ch in cleaned
        if ch in "\t\n\r" or ord(ch) >= 0x20
    )
    # Some public feeds/proxies prepend a few bytes before the XML declaration.
    # Remove only leading junk; never invent feed content.
    xml_start = cleaned.find("<")
    if xml_start > 0:
        cleaned = cleaned[xml_start:]
    root = ET.fromstring(cleaned)
    # RSS 2.0 and Atom both appear in public economic feeds.
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if tag not in {"item", "entry"}:
            continue
        row = {}
        for child in list(node):
            key = child.tag.rsplit("}", 1)[-1].lower()
            if key == "link" and child.attrib.get("href"):
                row["link"] = child.attrib["href"]
            elif child.text:
                row[key] = child.text
        if row:
            yield row


def _to_item(source: NewsSource, row: dict, detected_at: datetime) -> NewsItem | None:
    headline = _clean_text(row.get("title"))
    url = (row.get("link") or row.get("guid") or "").strip()
    summary = _clean_text(row.get("description") or row.get("summary") or row.get("content"))
    if not headline or not url:
        return None

    external_raw = (row.get("guid") or row.get("id") or url or headline).strip()
    external_id = hashlib.sha256(external_raw.encode("utf-8")).hexdigest()[:40]
    text = f"{headline} {summary}"
    return NewsItem(
        source=source.key,
        external_id=external_id,
        headline=headline,
        summary=summary or None,
        url=url,
        published_at=_parse_time(row.get("pubdate") or row.get("published") or row.get("updated")),
        detected_at=detected_at.isoformat(),
        category=_category(text),
        relevance=_relevance(text),
        rights_status=source.rights_status,
    )


def collect_news(
    *,
    detected_at: datetime | None = None,
    timeout_seconds: int = 15,
    max_items_per_source: int = 8,
) -> list[NewsItem]:
    now = detected_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("DETECTED_AT_MUST_BE_TIMEZONE_AWARE")

    output: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    source_errors: list[str] = []

    for source in NEWS_SOURCES:
        try:
            response = requests.get(
                source.url,
                timeout=timeout_seconds,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Intraday-Oi-News/1.0)",
                    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1",
                },
            )
            response.raise_for_status()
            headers = getattr(response, "headers", {}) or {}
            content_type = (headers.get("content-type") or "").lower()
            body = response.text
            if "html" in content_type and source.key == "BEA_RELEASES":
                # BEA may serve its releases page instead of the RSS document.
                # Keep the source-backed page usable without inventing dates.
                links = re.findall(
                    r'href=["\']([^"\']*/news/[^"\']+)["\'][^>]*>(.*?)</a>',
                    body,
                    flags=re.I | re.S,
                )
                rows = [
                    {
                        "title": _clean_text(title),
                        "link": ("https://www.bea.gov" + href) if href.startswith("/") else href,
                    }
                    for href, title in links
                    if _clean_text(title)
                ]
            else:
                rows = list(_xml_rows(body))
            for row in rows[: max(1, int(max_items_per_source))]:
                item = _to_item(source, row, now)
                if item is None or item.relevance == "LOW":
                    continue
                key = (item.source, item.external_id)
                if key in seen:
                    continue
                seen.add(key)
                output.append(item)
        except Exception as exc:
            source_errors.append(f"{source.key}:{type(exc).__name__}:{exc}")

    output.sort(
        key=lambda item: (
            item.published_at is not None,
            item.published_at or "",
        ),
        reverse=True,
    )
    if source_errors:
        # Preserve partial success; diagnostics are returned to logs, never to
        # customer-facing text as if they were market facts.
        print("⚠️  News source errors: " + " | ".join(source_errors)[:1800])
    return output


def format_news_announcement(items: list[NewsItem | dict], *, limit: int = 3) -> str:
    """Render concise source-backed news announcements."""
    rows = items[: max(1, int(limit))]
    lines = ["<b>🚨 NEWS ANNOUNCEMENT</b>", ""]
    for row in rows:
        if isinstance(row, dict):
            category = row.get("category") or "OTHER"
            headline = row.get("headline") or "UNKNOWN"
            source = row.get("source") or "UNKNOWN"
            published = row.get("published_at") or "UNKNOWN"
            url = row.get("url") or ""
        else:
            category = row.category
            headline = row.headline
            source = row.source
            published = row.published_at or "UNKNOWN"
            url = row.url

        lines.extend([
            f"<b>{html.escape(str(category))}</b>",
            html.escape(str(headline)),
            f"Source: {html.escape(str(source))} | {html.escape(str(published))}",
            html.escape(str(url)),
            "",
        ])
    lines.append("หมายเหตุ: source announcement เท่านั้น • Analyst จะนำไปพิจารณาร่วมกับ market evidence")
    return "\n".join(lines).strip()
