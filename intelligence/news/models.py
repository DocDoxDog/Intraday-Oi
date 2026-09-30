from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class NewsSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    IGNORE = "IGNORE"


class ImpactDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    UNCERTAIN = "UNCERTAIN"


class NewsStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class NewsItem:
    news_id: str
    headline: str
    source: str
    url: str
    published_at: datetime
    detected_at: datetime
    event_time: datetime | None = None
    language: str = "en"
    category: str = "UNKNOWN"
    entities: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    severity: NewsSeverity = NewsSeverity.MEDIUM
    status: NewsStatus = NewsStatus.PENDING
    provenance_id: str | None = None


@dataclass(frozen=True)
class StoryCluster:
    cluster_id: str
    canonical_headline: str
    news_ids: tuple[str, ...]
    source_count: int
    first_published_at: datetime
    last_published_at: datetime
    official_source: bool


@dataclass(frozen=True)
class MarketConfirmation:
    confirmed: bool
    score: float
    price_reaction: float | None
    volatility_reaction: float | None
    oi_change: float | None
    gex_change: float | None
    dex_change: float | None
    market_state_changed: bool
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewsImpact:
    news_id: str
    story_cluster_id: str
    severity: NewsSeverity
    confidence: float
    assets: tuple[str, ...]
    direction: ImpactDirection
    horizon: str
    impact_reason: tuple[str, ...]
    source_count: int
    official_source: bool
    market_confirmation: MarketConfirmation
    model_version: str


@dataclass(frozen=True)
class NewsPriority:
    news_id: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
