from datetime import datetime, timezone

from intelligence.analytics import ProductEvent, product_event


def test_product_event_is_timezone_aware():
    event = product_event(
        "dashboard_view",
        "WEB",
        organization_id="org1",
        metadata={"page": "overview"},
    )
    assert event.channel == "WEB"
    assert event.organization_id == "org1"
    assert event.occurred_at.tzinfo is not None
