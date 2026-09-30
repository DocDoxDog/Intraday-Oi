from datetime import date

from quant.contracts import (
    Contract,
    Expiration,
    Future,
    Instrument,
    OptionContract,
    OptionType,
    Strike,
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
        expiry=__import__("datetime").datetime(2026, 12, 29, tzinfo=__import__("datetime").timezone.utc),
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
    assert option.canonical_key.endswith(":4300:CALL")


def test_legacy_contract_alias_is_same_canonical_model():
    assert Contract is OptionContract
    assert normalize_option_type("c") is OptionType.CALL
