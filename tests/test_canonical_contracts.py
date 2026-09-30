from datetime import date, datetime, timezone

import pytest

from quant.contracts import (
    Contract,
    Expiration,
    Future,
    Instrument,
    OptionContract,
    OptionType,
    Strike,
    build_option_contract,
    normalize_option_type,
)


def test_canonical_model_has_explicit_entities():
    instrument = Instrument("GC", "GC", "COMEX", "FUTURE", "USD")
    future = Future(
        instrument_id=instrument.instrument_id,
        contract_code="GCZ6",
        root="GC",
        exchange="COMEX",
        expiration=date(2026, 12, 29),
        multiplier=100.0,
        currency="USD",
    )
    expiry = Expiration(
        underlying="GC",
        expiry=datetime(2026, 12, 29, tzinfo=timezone.utc),
    )
    strike = Strike("GC", 4300.0)
    option = OptionContract(
        symbol="OG",
        root="OG",
        exchange="COMEX",
        underlying="GC",
        option_type=OptionType.CALL,
        expiration=date(2026, 12, 24),
        strike=4300.0,
        multiplier=100.0,
        currency="USD",
        settlement_type="DELIVERABLE",
        source="cme",
        instrument_id=instrument.instrument_id,
        future_id=future.future_id,
        expiration_id=expiry.expiration_id,
        strike_id=strike.strike_id,
    )
    assert instrument.instrument_id
    assert future.future_id
    assert expiry.expiration_id
    assert strike.strike_id
    assert option.canonical_id
    assert option.resolution_status == "RESOLVED"


def test_unresolved_contract_does_not_guess_metadata():
    contract = build_option_contract({
        "root": "OG",
        "underlying": "GC",
        "exchange": "COMEX",
        "option_type": "C",
        "source": "quikstrike",
    })
    assert contract.resolution_status == "UNRESOLVED"
    assert contract.expiration is None
    assert contract.multiplier is None


def test_legacy_contract_alias_is_canonical_model():
    assert Contract is OptionContract
    assert normalize_option_type("c") == OptionType.CALL


def test_explicit_option_metadata_produces_stable_id():
    contract = build_option_contract({
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
    assert contract.resolution_status == "RESOLVED"
    assert contract.canonical_id
