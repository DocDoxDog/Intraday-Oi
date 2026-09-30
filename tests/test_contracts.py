from datetime import date

from src.contracts import Contract, OptionType, normalize_option_type


def test_normalize_option_type():
    assert normalize_option_type("c") is OptionType.CALL
    assert normalize_option_type("PUT") is OptionType.PUT


def test_canonical_option_key_is_stable():
    contract = Contract(
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
    )
    assert contract.canonical_key == "COMEX:OG:GC:2026-12-24:4300:CALL"


def test_unknown_metadata_is_not_invented():
    contract = Contract(
        symbol="UNKNOWN",
        root="OG",
        exchange="COMEX",
        underlying="GC",
        option_type=None,
        expiration=None,
        strike=None,
        multiplier=None,
        currency=None,
        settlement_type=None,
        source="unknown",
    )
    assert contract.canonical_key.endswith(":UNKNOWN_EXPIRY:UNKNOWN_STRIKE:FUTURE")
