from datetime import datetime, timezone

from quant.raw import RawMarketData, dataset_version, payload_checksum


def test_raw_payload_checksum_is_deterministic():
    payload = {"b": 2, "a": [1, 2, 3]}
    assert payload_checksum(payload) == payload_checksum({"a": [1, 2, 3], "b": 2})


def test_raw_market_data_has_reproducible_dataset_version():
    raw = RawMarketData.create(
        source="quikstrike",
        payload={"strike": 4300, "oi": 100},
        source_version="image-map-v1",
        fetched_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
    )
    assert raw.checksum
    assert raw.dataset_version == dataset_version(
        source="quikstrike",
        source_version="image-map-v1",
        checksum=raw.checksum,
    )
