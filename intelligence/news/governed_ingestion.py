from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from intelligence.news.ingestion import NewsSourceAdapter
from intelligence.news.models import NewsItem
from intelligence.news.provenance import NewsProvenance
from intelligence.news.source_registry import NewsSourcePolicy, RightsStatus
from intelligence.news.normalization import normalize_news


@dataclass(frozen=True)
class IngestedNews:
    item: NewsItem
    provenance: NewsProvenance
    customer_distribution_allowed: bool


class GovernedNewsIngestor:
    """News ingest boundary that carries rights status with every item."""

    def __init__(self, policy: NewsSourcePolicy, adapter: NewsSourceAdapter):
        self.policy = policy
        self.adapter = adapter

    def run(self, *, detected_at: datetime | None = None) -> list[IngestedNews]:
        now = detected_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("DETECTED_AT_MUST_BE_TIMEZONE_AWARE")
        rows = self.adapter.collect()
        output: list[IngestedNews] = []
        for row in rows:
            item = normalize_news(
                row, detected_at=now,
            )
            provenance = NewsProvenance(
                provenance_id=item.news_id + ":prov",
                source=self.policy.source,
                url=item.url,
                published_at=item.published_at,
                detected_at=item.detected_at,
                retrieval_method=self.policy.access_method,
                rights_status=self.policy.rights_status.value,
                retention_policy="SOURCE_POLICY_DEFAULT",
            )
            allowed = self.policy.allows_customer_distribution(now.date())
            output.append(IngestedNews(item, provenance, allowed))
        return output