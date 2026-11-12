from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
from typing import Any

from intelligence.news.dedupe import cluster_news
from intelligence.news.normalization import normalize_news


_SOURCE_SCORE = {
    "FED_MONETARY": 24,
    "BLS_EMPLOYMENT": 24,
    "BLS_CPI": 24,
    "BLS_PPI": 24,
    "BLS_JOLTS": 24,
    "BEA_RELEASES": 24,
    "CME": 24,
    "Forex Factory": 18,
    "GDELT": 12,
}

_OFFICIAL_SOURCES = {
    "FED_MONETARY",
    "BLS_EMPLOYMENT",
    "BLS_CPI",
    "BLS_PPI",
    "BLS_JOLTS",
    "BEA_RELEASES",
    "CME",
}

_EVENT_WORDS = {
    "MONETARY_POLICY": ("fomc", "fed", "interest rate", "rate decision", "rate cut", "rate hike", "monetary"),
    "INFLATION": ("cpi", "ppi", "pce", "inflation", "consumer price", "producer price"),
    "LABOR": ("payroll", "employment", "unemployment", "jobless", "jobs report", "jolts", "wages"),
    "GROWTH": ("gdp", "growth", "consumer spending", "retail sales", "personal income"),
    "RATES_LIQUIDITY": ("treasury", "yield", "real yield", "liquidity", "balance sheet", "yield curve"),
    "GEOPOLITICAL": ("war", "conflict", "missile", "airstrike", "invasion", "sanctions", "ceasefire", "military", "attack"),
    "GOLD_DEMAND": ("gold", "central bank", "gold etf", "reserve", "bullion"),
}

_GEO_SUPPORTIVE = ("war", "conflict", "missile", "airstrike", "invasion", "sanctions", "military", "attack", "escalation")
_GEO_RELIEF = ("ceasefire", "truce", "de-escalation", "peace deal", "peace talks")
_UNEMPLOYMENT_WORDS = ("unemployment", "jobless")
_SURPRISE_RE = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|[KMB])?", re.IGNORECASE)


def _num(value: object) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    match = _SURPRISE_RE.search(text)
    if not match:
        return None
    token = match.group(0).replace("%", "").strip()
    multiplier = 1.0
    if token.upper().endswith("K"):
        multiplier = 1_000.0
        token = token[:-1]
    elif token.upper().endswith("M"):
        multiplier = 1_000_000.0
        token = token[:-1]
    elif token.upper().endswith("B"):
        multiplier = 1_000_000_000.0
        token = token[:-1]
    try:
        return float(token) * multiplier
    except ValueError:
        return None


def _age_hours(published_at: object, detected_at: datetime) -> float | None:
    if not published_at:
        return None
    try:
        value = published_at if isinstance(published_at, datetime) else datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        if value.tzinfo is None:
            return None
        return max(0.0, (detected_at.astimezone(timezone.utc) - value.astimezone(timezone.utc)).total_seconds() / 3600.0)
    except (TypeError, ValueError):
        return None


def _source_score(source: str) -> int:
    if source in _SOURCE_SCORE:
        return _SOURCE_SCORE[source]
    lowered = source.lower()
    if "reuters" in lowered or "bloomberg" in lowered or "cme" in lowered:
        return 22
    if "government" in lowered or ".gov" in lowered:
        return 22
    if "forex factory" in lowered:
        return 18
    if "gdelt" in lowered:
        return 12
    return 8


def _source_tier(source: str) -> str:
    if source in _OFFICIAL_SOURCES or source.upper().endswith("_RELEASES") or source.upper().startswith("BLS_"):
        return "OFFICIAL"
    if "forex factory" in source.lower():
        return "CALENDAR"
    if "gdelt" in source.lower():
        return "DISCOVERY"
    return "MARKET_SOURCE"


def _market_relevance(item: dict[str, Any]) -> tuple[int, list[str]]:
    text = f"{item.get('headline') or ''} {item.get('summary') or ''}".lower()
    channels = [str(x).upper() for x in (item.get("market_channels") or [])]
    hits: list[str] = []
    for category, keywords in _EVENT_WORDS.items():
        if any(keyword in text for keyword in keywords):
            hits.append(category)

    score = 4
    if "GOLD" in channels or "GOLD_DEMAND" in hits:
        score = max(score, 15)
    if any(x in channels for x in ("RATES", "REAL_YIELD", "USD", "LIQUIDITY")) or any(x in hits for x in ("MONETARY_POLICY", "RATES_LIQUIDITY")):
        score = max(score, 14)
    if any(x in channels for x in ("INFLATION", "LABOR", "GROWTH")) or any(x in hits for x in ("INFLATION", "LABOR", "GROWTH")):
        score = max(score, 12)
    if "RISK_SENTIMENT" in channels or "GEOPOLITICAL" in hits:
        score = max(score, 11)
    return score, hits


def _surprise_info(item: dict[str, Any]) -> dict[str, Any]:
    actual = _num(item.get("actual"))
    forecast = _num(item.get("forecast"))
    previous = _num(item.get("previous"))
    if actual is None or forecast is None:
        return {
            "status": "UNAVAILABLE",
            "actual": actual,
            "forecast": forecast,
            "previous": previous,
            "delta": None,
            "direction": "UNKNOWN",
        }
    delta = actual - forecast
    return {
        "status": "AVAILABLE",
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "delta": round(delta, 8),
        "direction": "ABOVE_FORECAST" if delta > 0 else "BELOW_FORECAST" if delta < 0 else "AT_FORECAST",
    }


def _gold_bias(item: dict[str, Any], surprise: dict[str, Any], categories: list[str]) -> tuple[str, str, list[str]]:
    text = f"{item.get('headline') or ''} {item.get('summary') or ''}".lower()
    direction = surprise.get("direction")
    if "GEOPOLITICAL" in categories:
        if any(word in text for word in _GEO_SUPPORTIVE):
            return "POTENTIALLY_SUPPORTIVE", "risk-off / safe-haven channel", ["geopolitical risk headline", "observe Gold price response"]
        if any(word in text for word in _GEO_RELIEF):
            return "POTENTIALLY_NEGATIVE", "risk-relief channel", ["de-escalation headline", "observe Gold price response"]
        return "UNKNOWN", "headline alone is not enough", ["wait for price / volatility response"]

    if not direction:
        if "GOLD_DEMAND" in categories:
            return "POTENTIALLY_SUPPORTIVE", "gold-demand channel", ["gold demand / reserve theme", "observe confirmation in price and flow"]
        return "UNKNOWN", "no validated surprise value", ["headline is context, not a trade trigger"]

    if any(cat in categories for cat in ("MONETARY_POLICY", "INFLATION", "RATES_LIQUIDITY", "GROWTH")):
        if direction == "ABOVE_FORECAST":
            return "POTENTIALLY_NEGATIVE", "higher macro pressure can support yields / USD", ["actual above forecast", "watch US yields / USD", "watch Gold response"]
        if direction == "BELOW_FORECAST":
            return "POTENTIALLY_SUPPORTIVE", "softer macro pressure can reduce yields / USD support", ["actual below forecast", "watch US yields / USD", "watch Gold response"]
        return "MIXED", "release was near forecast", ["watch the post-release market response"]

    if "LABOR" in categories:
        weaker_is_supportive = any(word in text for word in _UNEMPLOYMENT_WORDS)
        if weaker_is_supportive:
            if direction == "ABOVE_FORECAST":
                return "POTENTIALLY_SUPPORTIVE", "higher unemployment can reduce rate pressure", ["actual above forecast", "watch yields / USD"]
            if direction == "BELOW_FORECAST":
                return "POTENTIALLY_NEGATIVE", "lower unemployment can reinforce rate pressure", ["actual below forecast", "watch yields / USD"]
        else:
            if direction == "ABOVE_FORECAST":
                return "POTENTIALLY_NEGATIVE", "stronger labor data can reinforce rate pressure", ["actual above forecast", "watch yields / USD"]
            if direction == "BELOW_FORECAST":
                return "POTENTIALLY_SUPPORTIVE", "softer labor data can reduce rate pressure", ["actual below forecast", "watch yields / USD"]

    return "UNKNOWN", "not enough validated context", ["do not convert headline into a trade signal"]


def _why_it_matters(item: dict[str, Any], bias: str, surprise: dict[str, Any], categories: list[str]) -> str:
    if surprise["status"] == "AVAILABLE":
        a = item.get("actual")
        f = item.get("forecast")
        return f"Actual {a} vs Forecast {f} → {bias.replace('_', ' ').lower()}; confirm with yields, USD and Gold price response."
    if "GEOPOLITICAL" in categories:
        return "Geopolitical headline can change safe-haven demand, but direction must be confirmed by price and volatility response."
    if "GOLD_DEMAND" in categories:
        return "Gold-demand headline is structurally relevant; use it as context and wait for price/flow confirmation."
    return "Relevant macro context; no validated surprise value, so it should not drive a trade by itself."


def _freshness_score(age_hours: float | None) -> int:
    if age_hours is None:
        return 4
    if age_hours <= 1:
        return 24
    if age_hours <= 6:
        return 20
    if age_hours <= 24:
        return 15
    if age_hours <= 72:
        return 8
    return 2


def rank_news(items: list[dict[str, Any]], *, detected_at: datetime | None = None) -> list[dict[str, Any]]:
    now = detected_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("DETECTED_AT_MUST_BE_TIMEZONE_AWARE")
    if not items:
        return []

    normalized: list[dict[str, Any]] = []
    typed = []
    normalized_by_key: dict[tuple[str, str, str, str], Any] = {}
    for raw in items:
        row = dict(raw)
        try:
            published_value = row.get("published_at")
            if not isinstance(published_value, datetime):
                parsed_published = datetime.fromisoformat(str(published_value).replace("Z", "+00:00"))
                if parsed_published.tzinfo is None:
                    parsed_published = parsed_published.replace(tzinfo=timezone.utc)
                row["published_at"] = parsed_published.astimezone(timezone.utc)
            parsed = normalize_news(row, detected_at=now)
            typed.append(parsed)
            key = (
                str(row.get("source") or "").strip().lower(),
                str(row.get("url") or "").strip(),
                str(row.get("published_at") or "").strip(),
                str(row.get("headline") or "").strip().lower(),
            )
            normalized_by_key[key] = parsed
        except (TypeError, ValueError):
            continue
    if typed:
        clusters = cluster_news(typed)
        cluster_map = {
            news_id: cluster
            for cluster in clusters
            for news_id in cluster.news_ids
        }
    else:
        cluster_map = {}

    cluster_source_count: dict[str, int] = {}
    cluster_members: dict[str, list[str]] = defaultdict(list)
    for news_id, cluster in cluster_map.items():
        cluster_source_count[cluster.cluster_id] = cluster.source_count
        cluster_members[cluster.cluster_id].append(news_id)

    for item in items:
        row = dict(item)
        published = row.get("published_at")
        age = _age_hours(published, now)
        source = str(row.get("source") or "UNKNOWN")
        freshness = _freshness_score(age)
        source_score = _source_score(source)
        relevance_score, categories = _market_relevance(row)
        severity_map = {"CRITICAL": 25, "HIGH": 21, "MEDIUM": 13, "LOW": 5, "IGNORE": 0}
        severity = severity_map.get(str(row.get("severity") or "MEDIUM").upper(), 8)
        surprise = _surprise_info(row)
        surprise_bonus = 12 if surprise["status"] == "AVAILABLE" else 0
        normalized_key = (
            str(row.get("source") or "").strip().lower(),
            str(row.get("url") or "").strip(),
            str(row.get("published_at") or "").strip(),
            str(row.get("headline") or "").strip().lower(),
        )
        normalized_item = normalized_by_key.get(normalized_key)
        cluster = cluster_map.get(normalized_item.news_id) if normalized_item is not None else None
        if cluster is None:
            canonical = str(row.get("headline") or "").strip().lower()
            cluster_id = f"story-{abs(hash(canonical)) % 1000000:06d}"
            source_count = 1
        else:
            cluster_id = cluster.cluster_id
            source_count = cluster.source_count
        cross_source_bonus = min(8, max(0, source_count - 1) * 4)

        # Components are intentionally additive: each represents a distinct
        # piece of evidence. The raw total is capped to 100 so an official,
        # fresh, highly relevant release with an actual-vs-forecast surprise
        # naturally reaches HIGH/CRITICAL instead of being compressed into LOW.
        score = max(0, min(100, int(round(
            freshness
            + source_score
            + relevance_score
            + severity
            + surprise_bonus
            + cross_source_bonus
        ))))

        bias, channel, evidence = _gold_bias(row, surprise, categories)
        row.update({
            "news_score": score,
            "impact_tier": "CRITICAL" if score >= 85 else "HIGH" if score >= 70 else "MEDIUM" if score >= 50 else "LOW",
            "source_tier": _source_tier(source),
            "source_quality_score": source_score,
            "freshness_score": freshness,
            "story_age_hours": round(age, 2) if age is not None else None,
            "market_relevance_score": relevance_score,
            "detected_categories": categories,
            "surprise": surprise,
            "gold_bias": bias,
            "gold_channel": channel,
            "evidence_chain": evidence,
            "why_it_matters": _why_it_matters(row, bias, surprise, categories),
            "story_cluster_id": cluster_id.cluster_id if hasattr(cluster_id, "cluster_id") else str(cluster_id),
            "cross_source_count": source_count,
            "cross_source_confirmed": source_count >= 2,
            "actionability": "WATCH_NOW" if score >= 80 else "WATCH" if score >= 60 else "CONTEXT" if score >= 40 else "BACKGROUND",
        })
        normalized.append(row)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        grouped[str(row.get("story_cluster_id"))].append(row)

    primaries: dict[str, dict[str, Any]] = {}
    for cluster_id, rows in grouped.items():
        rows.sort(key=lambda x: (x.get("news_score", 0), x.get("published_at") or ""), reverse=True)
        primary_id = str(rows[0].get("external_id") or rows[0].get("news_id") or "")
        for idx, row in enumerate(rows):
            row["story_primary"] = idx == 0
            row["story_primary_id"] = primary_id
        primaries[cluster_id] = rows[0]

    return sorted(
        normalized,
        key=lambda x: (
            bool(x.get("story_primary")),
            int(x.get("news_score") or 0),
            x.get("published_at") or "",
        ),
        reverse=True,
    )


def build_news_intelligence(items: list[dict[str, Any]], *, detected_at: datetime | None = None, top_n: int = 8) -> dict[str, Any]:
    ranked = rank_news(items, detected_at=detected_at)
    primaries = []
    seen: set[str] = set()
    for row in ranked:
        cluster = str(row.get("story_cluster_id") or "")
        if not row.get("story_primary") or cluster in seen:
            continue
        seen.add(cluster)
        primaries.append(row)
        if len(primaries) >= max(1, int(top_n)):
            break

    channels: dict[str, int] = defaultdict(int)
    tiers: dict[str, int] = defaultdict(int)
    for row in ranked:
        for channel in row.get("detected_categories") or []:
            channels[str(channel)] += 1
        tiers[str(row.get("source_tier") or "UNKNOWN")] += 1

    return {
        "version": "news-intelligence-v2",
        "as_of": (detected_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "total_items": len(ranked),
        "primary_stories": primaries,
        "all_ranked": ranked,
        "market_categories": dict(sorted(channels.items(), key=lambda x: (-x[1], x[0]))),
        "source_tiers": dict(sorted(tiers.items(), key=lambda x: (-x[1], x[0]))),
        "limitations": [
            "gold_bias is a directional hypothesis, not observed price response",
            "headline/news does not become a trade trigger without market confirmation",
        ],
    }
