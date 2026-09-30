from datetime import datetime, timezone, timedelta

import pytest

from intelligence.cfd_mapping import CfdMapping


def test_cfd_mapping_active_window():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    mapping = CfdMapping(
        broker="example",
        cfd_symbol="XAUUSD",
        canonical_reference="GC",
        mapping_version="v1",
        effective_from=start,
        effective_to=start + timedelta(days=10),
    )
    assert mapping.active_at(start + timedelta(days=1))
    assert not mapping.active_at(start + timedelta(days=11))


def test_cfd_mapping_rejects_naive_time():
    mapping = CfdMapping(
        broker="example",
        cfd_symbol="XAUUSD",
        canonical_reference="GC",
        mapping_version="v1",
        effective_from=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="MAPPING_TIMES_MUST_BE_TIMEZONE_AWARE"):
        mapping.active_at(datetime(2026, 10, 2))
