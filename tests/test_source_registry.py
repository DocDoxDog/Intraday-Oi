from datetime import date

from intelligence.news.source_registry import (
    DEFAULT_SOURCE_POLICIES,
    RightsStatus,
)


def test_unlicensed_sources_cannot_be_customer_distributed():
    reuters = next(x for x in DEFAULT_SOURCE_POLICIES if x.source == "Reuters")
    assert reuters.rights_status in {RightsStatus.LICENSE_REQUIRED, RightsStatus.LEGAL_REVIEW_REQUIRED}
    assert not reuters.allows_customer_distribution(date(2026, 10, 1))
