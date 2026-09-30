from datetime import datetime, timedelta, timezone

from commercial.source_rights import RightsState, SourceRights, can_distribute

def test_customer_surface_requires_explicit_right():
    rights = SourceRights(
        source_id="cme-gc",
        state=RightsState.APPROVED,
        customer_display=True,
        api_distribution=False,
        alert_distribution=True,
    )
    assert can_distribute(rights, surface="CUSTOMER_DISPLAY")
    assert not can_distribute(rights, surface="API")
    assert can_distribute(rights, surface="ALERT")

def test_license_required_blocks_every_customer_surface():
    rights = SourceRights(
        source_id="news-x",
        state=RightsState.LICENSE_REQUIRED,
        customer_display=True,
        api_distribution=True,
        alert_distribution=True,
    )
    assert not can_distribute(rights, surface="CUSTOMER_DISPLAY")

def test_inactive_agreement_blocks_distribution():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    rights = SourceRights(
        source_id="cme-gc",
        state=RightsState.APPROVED,
        customer_display=True,
        effective_from=now + timedelta(days=1),
    )
    assert not can_distribute(rights, surface="CUSTOMER_DISPLAY", now=now)
