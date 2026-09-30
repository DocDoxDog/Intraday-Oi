from datetime import datetime, timedelta, timezone

from commercial.market_state import CommercialMarketStateEnvelope, MarketDataStatus, RightsStatus

NOW = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)

def make_state(**overrides):
    values = dict(
        symbol="GC",
        as_of=NOW - timedelta(seconds=10),
        publication_time=NOW - timedelta(seconds=60),
        availability_time=NOW - timedelta(seconds=50),
        ingestion_time=NOW - timedelta(seconds=5),
        data_status=MarketDataStatus.VALID,
        data_quality=0.98,
        data_age_seconds=50,
        dataset_version="dataset-v1",
        calculation_version="gex-v1",
        rights_status=RightsStatus.APPROVED,
    )
    values.update(overrides)
    return CommercialMarketStateEnvelope(**values)

def test_valid_point_in_time_market_state():
    ok, errors = make_state().validate(now=NOW)
    assert ok is True
    assert errors == ()

def test_future_as_of_is_rejected():
    ok, errors = make_state(as_of=NOW + timedelta(minutes=1)).validate(now=NOW)
    assert ok is False
    assert "AS_OF_IN_FUTURE" in errors

def test_missing_publication_time_is_rejected():
    ok, errors = make_state(publication_time=None).validate(now=NOW)
    assert ok is False
    assert "PUBLICATION_TIME_REQUIRED" in errors

def test_availability_after_as_of_is_rejected():
    ok, errors = make_state(
        availability_time=NOW,
        as_of=NOW - timedelta(seconds=10),
    ).validate(now=NOW)
    assert ok is False
    assert "AVAILABILITY_AFTER_AS_OF" in errors

def test_unapproved_rights_are_rejected():
    ok, errors = make_state(rights_status=RightsStatus.LICENSE_REQUIRED).validate(now=NOW)
    assert ok is False
    assert "DATA_RIGHTS_NOT_APPROVED:LICENSE_REQUIRED" in errors

def test_stale_state_is_rejected():
    ok, errors = make_state(data_age_seconds=121).validate(now=NOW)
    assert ok is False
    assert "DATA_TOO_OLD" in errors
