from datetime import datetime, timezone

from intelligence.news.governed_ingestion import GovernedNewsIngestor
from intelligence.news.ingestion import NewsSourceAdapter
from intelligence.news.source_registry import RightsStatus, NewsSourcePolicy


def test_governed_ingestion_carries_rights_status():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    policy = NewsSourcePolicy(
        source="Test", access_method="rss", rights_status=RightsStatus.LEGAL_REVIEW_REQUIRED,
        commercial_use=False, redistribution=False, attribution_required=True, retention_days=None,
        effective_from=now.date(),
    )
    adapter = NewsSourceAdapter(
        "Test", lambda: [{"headline": "Fed", "source": "Test", "url": "https://example.test/fed", "published_at": now}]
    )
    rows = GovernedNewsIngestor(policy, adapter).run(detected_at=now)
    assert rows[0].provenance.rights_status == "LEGAL_REVIEW_REQUIRED"
    assert rows[0].customer_distribution_allowed is False