from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo
import html as html_lib
import re

import requests

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FOREX_FACTORY_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FOREX_FACTORY_HTML_URL = "https://www.forexfactory.com/calendar"
FOREX_FACTORY_TZ = ZoneInfo("Europe/London")


def _get(url: str, *, params: dict[str, Any] | None = None, timeout: int = 20):
    r = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "Intraday-Oi-News/2.0"},
    )
    r.raise_for_status()
    return r


def _clean_calendar_text(value: object) -> str:
    if value is None:
        return ""
    text = html_lib.unescape(str(value))
    return re.sub(r"\s+", " ", text).strip()


def _canonical_title(value: object) -> str:
    return _clean_calendar_text(value).casefold()


def _calendar_value(value: object) -> str | None:
    text = _clean_calendar_text(value)
    if text in {"", "-", "—", "–", "n/a", "N/A", "NA"}:
        return None
    return text


def _event_time_from_html_row(row: dict[str, str], *, year: int) -> datetime | None:
    date_text = _clean_calendar_text(row.get("date"))
    time_text = _clean_calendar_text(row.get("time"))
    if not date_text:
        return None
    if not time_text or time_text.lower().startswith("all day") or time_text.lower().startswith("day "):
        time_text = "12:00am"
    try:
        local_dt = datetime.strptime(
            f"{year} {date_text} {time_text}",
            "%Y %a %b %d %I:%M%p",
        ).replace(tzinfo=FOREX_FACTORY_TZ)
    except ValueError:
        return None
    return local_dt.astimezone(timezone.utc)


class _ForexFactoryCalendarParser(HTMLParser):
    """Parse only source-backed calendar cells from Forex Factory HTML.

    The parser deliberately ignores visual/graph details. It uses the
    documented calendar row/cell classes and carries the date forward when the
    site leaves repeated date cells blank.
    """

    _FIELD_NAMES = {
        "date",
        "time",
        "currency",
        "event",
        "actual",
        "forecast",
        "previous",
        "impact",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._in_row = False
        self._current_field: str | None = None
        self._cell_text: list[str] = []
        self._row: dict[str, str] = {}
        self._last_date = ""

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        raw = dict(attrs).get("class") or ""
        return {part for part in raw.split() if part}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr" and "calendar__row" in self._classes(attrs):
            self._in_row = True
            self._current_field = None
            self._cell_text = []
            self._row = {}
            data_event = dict(attrs).get("data-eventid") or dict(attrs).get("data-event-id")
            if data_event:
                self._row["event_id"] = _clean_calendar_text(data_event)
            return

        if not self._in_row or tag != "td":
            return

        classes = self._classes(attrs)
        field = next(
            (candidate for candidate in self._FIELD_NAMES if any(
                cls == candidate or cls.endswith(f"__{candidate}")
                for cls in classes
            )),
            None,
        )
        self._current_field = field
        self._cell_text = []

    def handle_data(self, data: str) -> None:
        if self._in_row and self._current_field:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_row and self._current_field:
            value = _clean_calendar_text(" ".join(self._cell_text))
            if self._current_field == "date" and value:
                self._last_date = value
            self._row[self._current_field] = value
            self._current_field = None
            self._cell_text = []
            return

        if tag == "tr" and self._in_row:
            if self._last_date and not self._row.get("date"):
                self._row["date"] = self._last_date
            if self._row.get("currency") and self._row.get("event"):
                self.rows.append(dict(self._row))
            self._in_row = False
            self._current_field = None
            self._cell_text = []
            self._row = {}


def _parse_forex_factory_html(html_text: str) -> list[dict[str, str]]:
    parser = _ForexFactoryCalendarParser()
    parser.feed(html_text or "")
    parser.close()
    return parser.rows


def _html_calendar_index(
    rows: list[dict[str, str]],
    *,
    year: int,
) -> tuple[dict[tuple[str, str, str], list[dict[str, str]]], dict[tuple[str, str], list[dict[str, str]]]]:
    exact: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    by_title: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        country = _clean_calendar_text(row.get("currency")).upper()
        title = _canonical_title(row.get("event"))
        if not country or not title:
            continue
        event_dt = _event_time_from_html_row(row, year=year)
        candidate = dict(row)
        if event_dt is not None:
            exact[(country, title, event_dt.isoformat())].append(candidate)
        by_title[(country, title)].append(candidate)

    return exact, by_title


def _enrich_calendar_from_html(
    payload: list[dict[str, Any]],
    html_text: str,
    *,
    year: int,
) -> tuple[int, int]:
    rows = _parse_forex_factory_html(html_text)
    exact, by_title = _html_calendar_index(rows, year=year)

    matched = 0
    actual_enriched = 0
    used_fallback: set[tuple[str, str, int]] = set()

    for event in payload:
        country = str(event.get("country") or "").strip().upper()
        title = _canonical_title(event.get("title"))
        raw_dt = str(event.get("date") or "").strip()
        if not country or not title:
            continue

        event_dt: datetime | None = None
        try:
            event_dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
            if event_dt.tzinfo is None:
                event_dt = None
            else:
                event_dt = event_dt.astimezone(timezone.utc)
        except ValueError:
            pass

        row = None
        if event_dt is not None:
            candidates = exact.get((country, title, event_dt.isoformat()), [])
            if candidates:
                row = candidates.pop(0)

        # Fall back only when the title/currency pair is unique. This avoids
        # inventing values when the same event appears multiple times.
        if row is None:
            candidates = by_title.get((country, title), [])
            if len(candidates) == 1:
                row = candidates[0]
            elif len(candidates) > 1:
                signature = (country, title, len(candidates))
                if signature not in used_fallback:
                    used_fallback.add(signature)
                    row = candidates[0]

        calendar = event.setdefault("calendar", {})
        if row is None:
            continue

        matched += 1
        for field in ("actual", "forecast", "previous"):
            value = _calendar_value(row.get(field))
            if value is not None:
                calendar[field] = value
                calendar[f"{field}_source"] = "forexfactory_html"
                if field == "actual":
                    actual_enriched += 1
            elif _calendar_value(event.get(field)) is not None:
                calendar.setdefault(field, _calendar_value(event.get(field)))
                calendar.setdefault(f"{field}_source", "forexfactory_json")

        event["calendar"]["match"] = "EXACT_OR_UNIQUE"
    return matched, actual_enriched


def fetch_gdelt(
    query: str = "(war OR conflict OR missile OR sanctions OR ceasefire OR airstrike OR military OR invasion OR attack)",
    *,
    timespan: str = "24h",
    maxrecords: int = 25,
) -> list[dict[str, Any]]:
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
    out = []
    for a in (payload.get("articles", []) if isinstance(payload, dict) else []):
        title = str(a.get("title") or "").strip()
        url = str(a.get("url") or "").strip()
        seen = str(a.get("seendate") or "").strip()
        if not title or not url or not seen:
            continue
        try:
            ts = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append({
            "headline": title,
            "source": str(a.get("domain") or "GDELT"),
            "url": url,
            "published_at": ts,
            "language": str(a.get("language") or "en"),
            "category": "GEOPOLITICAL",
            "assets": ("GOLD", "USD", "USOIL", "UKOIL"),
            "severity": "MEDIUM",
        })
    return out


def fetch_forex_factory_calendar(
    *,
    url: str = FOREX_FACTORY_JSON_URL,
    html_url: str = FOREX_FACTORY_HTML_URL,
    enrich_html: bool = True,
) -> list[dict[str, Any]]:
    json_response = _get(url)
    payload = json_response.json()
    if not isinstance(payload, list):
        raise ValueError("FOREX_FACTORY_INVALID_PAYLOAD")

    calendar_retrieved_at = datetime.now(timezone.utc).isoformat()
    severity = {"High": "HIGH", "Medium": "MEDIUM", "Low": "LOW", "Holiday": "IGNORE"}
    out: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []

    for e in payload:
        if not isinstance(e, dict):
            continue
        title = str(e.get("title") or "").strip()
        country = str(e.get("country") or "").strip().upper()
        raw = str(e.get("date") or "").strip()
        if not title or not country or not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            dt = dt.astimezone(timezone.utc) if dt.tzinfo else None
        except ValueError:
            dt = None
        if dt is None:
            continue

        impact = str(e.get("impact") or "Low").strip()
        actual = _calendar_value(e.get("actual"))
        forecast = _calendar_value(e.get("forecast"))
        previous = _calendar_value(e.get("previous"))
        raw_events.append(e)
        out.append({
            "headline": f"{country} — {title}",
            "source": "Forex Factory",
            "url": "https://www.forexfactory.com/calendar/",
            "published_at": dt,
            "event_time": dt,
            "language": "en",
            "category": "MACRO",
            "entities": (country,),
            "assets": ("GOLD", "USD") if country == "USD" else ("GOLD",),
            "severity": severity.get(impact, "LOW"),
            "calendar": {
                "country": country,
                "impact": impact,
                "actual": actual,
                "actual_source": "forexfactory_json" if actual else None,
                "forecast": forecast,
                "forecast_source": "forexfactory_json" if forecast else None,
                "previous": previous,
                "previous_source": "forexfactory_json" if previous else None,
                "retrieved_at": calendar_retrieved_at,
                "source_url": url,
                "html_source_url": html_url,
                "data_status": "JSON_ONLY",
            },
        })

    if enrich_html and raw_events:
        try:
            html_response = _get(html_url)
            matched, actual_enriched = _enrich_calendar_from_html(
                raw_events,
                html_response.text,
                year=max(item["published_at"].year for item in out),
            )
            for row, event in zip(out, raw_events):
                row["calendar"].update(event.get("calendar") or {})
                row["calendar"]["data_status"] = "HTML_ENRICHED" if (
                    event.get("calendar", {}).get("match") == "EXACT_OR_UNIQUE"
                ) else "JSON_ONLY"
                row["calendar"]["matched_rows"] = matched
                row["calendar"]["actual_enriched_count"] = actual_enriched
            print(
                f"    Forex Factory calendar: JSON={len(out)} HTML matches={matched} actual_enriched={actual_enriched}"
            )
        except requests.RequestException as exc:
            for row in out:
                row["calendar"]["data_status"] = "JSON_ONLY_HTML_UNAVAILABLE"
            print(f"⚠️  Forex Factory HTML enrichment unavailable: {exc}")
        except Exception as exc:
            for row in out:
                row["calendar"]["data_status"] = "JSON_ONLY_HTML_PARSE_FAILED"
            print(f"⚠️  Forex Factory HTML enrichment failed: {type(exc).__name__}:{exc}")

    return out


def fetch_free_news_bundle(
    *,
    gdelt_query: str = "(war OR conflict OR missile OR sanctions OR ceasefire OR airstrike OR military OR invasion OR attack)",
    gdelt_timespan: str = "24h",
    gdelt_maxrecords: int = 25,
) -> list[dict[str, Any]]:
    out = []
    try:
        out.extend(fetch_gdelt(gdelt_query, timespan=gdelt_timespan, maxrecords=gdelt_maxrecords))
    except requests.RequestException as exc:
        print(f"⚠️  GDELT feed unavailable: {exc}")
    try:
        out.extend(fetch_forex_factory_calendar())
    except requests.RequestException as exc:
        print(f"⚠️  Forex Factory feed unavailable: {exc}")
    return out
