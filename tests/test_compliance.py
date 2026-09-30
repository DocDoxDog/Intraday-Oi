from datetime import datetime, timezone, timedelta

from intelligence.compliance.jurisdiction import (
    RegulatoryProfile,
    feature_allowed,
)


def test_unapproved_jurisdiction_feature_is_blocked():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    profile = RegulatoryProfile(
        jurisdiction="TH",
        customer_type="RETAIL",
        feature="SCENARIO_PLAN",
        enabled=True,
        legal_review_status="LEGAL_REVIEW_REQUIRED",
        effective_from=now - timedelta(days=1),
    )
    ok, reason = feature_allowed(
        (profile,),
        jurisdiction="TH",
        customer_type="RETAIL",
        feature="SCENARIO_PLAN",
        now=now,
    )
    assert ok is False
    assert reason == "LEGAL_REVIEW_REQUIRED"


def test_approved_feature_can_be_enabled_without_quant_changes():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    profile = RegulatoryProfile(
        jurisdiction="TH",
        customer_type="RETAIL",
        feature="MARKET_OVERVIEW",
        enabled=True,
        legal_review_status="APPROVED",
        effective_from=now - timedelta(days=1),
    )
    ok, reason = feature_allowed(
        (profile,),
        jurisdiction="TH",
        customer_type="RETAIL",
        feature="MARKET_OVERVIEW",
        now=now,
    )
    assert (ok, reason) == (True, "REGULATORY_FEATURE_ENABLED")
