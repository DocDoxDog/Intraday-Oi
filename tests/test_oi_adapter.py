from datetime import date, datetime, timezone

import pytest

from quant.contracts import build_option_contract
from quant.models import DataStatus
from quant.oi.adapter import observation_from_row


def resolved_put():
    return build_option_contract({
        "symbol": "OG",
        "root": "OG",
        "exchange": "COMEX",
        "underlying": "GC",
        "option_type": "PUT",
        "expiration": date(2026, 12, 24),
        "strike": 4300.0,
        "multiplier": 100.0,
        "currency": "USD",
        "settlement_type": "DELIVERABLE",
        "source": "cme",
        "source_contract_code": "OGZ6P4300",
        "instrument_id": "i",
        "future_id": "f",
        "expiration_id": "e",
        "strike_id": "s",
    })


def test_oi_observation_preserves_pit_timestamps():
    t = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    obs = observation_from_row(
        resolved_put(),
        {"oiPut": 123, "oiPutChange": -7, "volumePut": 88},
        trade_date=date(2026, 10, 1),
        observation_time=t,
        publication_time=t,
        availability_time=t,
        ingestion_time=t,
        calculation_time=t,
        dataset_version="fixture-v1",
        source="cme",
        data_status=DataStatus.OFFICIAL,
    )
    assert obs.oi == 123
    assert obs.oi_change == -7
    assert obs.volume == 88
    assert obs.availability_time == t
    assert obs.dataset_version == "fixture-v1"


def test_unresolved_contract_is_rejected():
    contract = build_option_contract({
        "root": "OG",
        "underlying": "GC",
        "exchange": "COMEX",
        "option_type": "C",
        "source": "quikstrike",
    })
    with pytest.raises(ValueError, match="UNRESOLVED"):
        observation_from_row(
            contract,
            {"oiCall": 10},
            trade_date=date(2026, 10, 1),
            observation_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
            publication_time=None,
            availability_time=None,
            ingestion_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
            calculation_time=None,
            dataset_version="fixture-v1",
            source="test",
        )
