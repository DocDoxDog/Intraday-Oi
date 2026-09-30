from datetime import date, datetime, timezone, timedelta

import pytest

from quant.contracts import OptionType
from quant.models import OIObservation, DataStatus
from quant.oi.engine import aggregate_oi
from quant.pit import is_available_at, require_available_at


UTC = timezone.utc


def make_row(availability):
    return OIObservation(
        observation_id="obs-1",
        instrument_id="instrument-1",
        expiration_id="exp-1",
        strike_id="strike-4300",
        trade_date=date(2026, 10, 1),
        observation_time=datetime(2026, 10, 1, 12, tzinfo=UTC),
        publication_time=availability - timedelta(minutes=5) if availability else None,
        availability_time=availability,
        ingestion_time=datetime(2026, 10, 1, 12, 30, tzinfo=UTC),
        calculation_time=datetime(2026, 10, 1, 12, 31, tzinfo=UTC),
        option_type=OptionType.CALL,
        oi=100,
        oi_change=10,
        volume=50,
        source="test-fixture",
        dataset_version="fixture-v1",
        data_status=DataStatus.OFFICIAL,
    )


def test_future_oi_cannot_leak_into_historical_decision():
    decision = datetime(2026, 10, 1, 12, tzinfo=UTC)
    later = make_row(datetime(2026, 10, 1, 13, tzinfo=UTC))
    assert not is_available_at(later, decision)
    assert require_available_at([later], decision) == []
    assert aggregate_oi([later], decision_time=decision)["count"] == 0


def test_available_oi_is_usable():
    decision = datetime(2026, 10, 1, 13, tzinfo=UTC)
    row = make_row(datetime(2026, 10, 1, 12, 45, tzinfo=UTC))
    assert row.is_available_at(decision)
    assert require_available_at([row], decision) == [row]


def test_naive_decision_time_is_rejected():
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        make_row(datetime(2026, 10, 1, 12, tzinfo=UTC)).is_available_at(
            datetime(2026, 10, 1, 12)
        )
