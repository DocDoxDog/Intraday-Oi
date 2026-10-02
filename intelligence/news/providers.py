from __future__ import annotations

"""Free news/calendar providers.

The adapters return only headline/metadata. They intentionally do not scrape or
store article bodies. Source URLs and timestamps remain part of provenance.
"""

import csv
import io
from datetime import datetime, timezone
from typing import Any

import requests

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FOREX_FACTORY_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _get(url: str, *, params: dict[str, Any] | None = None, timeout: int = 20) -> requests.Response:
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "Intraday-Oi-News/1.0"},
    )
    response.raise_for_status()
    return response


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("PUBLISHED_AT_MUST_BE_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def fetch_gdelt(
    query: str = '(war OR conflict OR missile OR sanctions OR ceasefire OR airstrike)',
    *,
    timespan: str = "1h",
    maxrecords: int = 25,
) -> list[dict[str, Any]]:
    """Fetch recent GDELT article metadata for geopolitical discovery."""
    payload = _get(
        GDELT_DOC_URL,
        params={
            "query": query,
            "mode": "artlist",
            "maxrecords": max(1, min(int(maxrecords), 250)),
            "timespan": timespan,
            "sort": "datedesc",
            "format": "json",
        },
    ).json()

    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for article in articles:
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        seen = str(article.get("seendate") or "").strip()
        if not title or not url or not seen:
            continue
        try:
            published_at = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append(
            {
                "headline": title,
                "source": str(article.get("domain") or "GDELT").strip(),
                "url": url,
                "published_at": published_at,
                "language": str(article.get("language") or "en"),
                "category": "GEOPOLITICAL",
                "assets": ("GOLD", "USD", "USOIL", "UKOIL"),
                "severity": "MEDIUM",
            }
        )
    return out


def fetch_forex_factory_calendar(
    *,
    url: str = FOREX_FACTORY_JSON_URL,
) -> list[dict[str, Any]]:
    """Fetch the weekly Forex Factory/Fair Economy calendar JSON export."""
    payload = _get(url).json()
    if not isinstance(payload, list):
        raise ValueError("FOREX_FACTORY_INVALID_PAYLOAD")

    severity_map = {
        "High": "HIGH",
        "Medium": "MEDIUM",
        "Low": "LOW",
        "Holiday": "IGNORE",
    }
    out: list[dict[str, Any]] = []
    for event in payload:
        if not isinstance(event, dict):
            continue
        title = str(event.get("title") or "").strip()
        raw_date = str(event.get("date") or "").strip()
        country = str(event.get("country") or "").strip().upper()
        if not title or not raw_date or not country:
            continue
        try:
            published_at = _parse_iso(raw_date)
        except ValueError:
            continue

        impact = str(event.get("impact") or "Low").strip()
        out.append(
            {
                "headline": f"{country} — {title}",
                "source": "Forex Factory",
                "url": "https://www.forexfactory.com/calendar/",
                "published_at": published_at,
                "language": "en",
                "category": "MACRO" if country in {"USD", "EUR", "GBP", "JPY", "CNY"} else "MACRO",
                "entities": (country,),
                "assets": ("GOLD", "USD") if country == "USD" else ("GOLD",),
                "severity": severity_map.get(impact, "LOW"),
                "event_time": published_at,
                "calendar": {
                    "country": country,
                    "impact": impact,
                    "forecast": str(event.get("forecast") or ""),
                    "previous": str(event.get("previous") or ""),
                },
            }
        )
    return out


def fetch_free_news_bundle(
    *,
    gdelt_query: str = '(war OR conflict OR missile OR sanctions OR ceasefire OR airstrike)',
    gdelt_timespan: str = "1h",
    gdelt_maxrecords: int = 25,
) -> list[dict[str, Any]]:
    """Collect free geopolitical + macro event metadata.

    Provider failures are isolated: one feed being unavailable must not erase
    the other feed's evidence.
    """
    out: list[dict[str, Any]] = []
    try:
        out.extend(
            fetch_gdelt(
                gdelt_query,
                timespan=gdelt_timespan,
                maxrecords=gdelt_maxrecords,
            )
        )
    except requests.RequestException:
        pass

    try:
        out.extend(fetch_forex_factory_calendar())
    except requests.RequestException:
        pass

    return out
