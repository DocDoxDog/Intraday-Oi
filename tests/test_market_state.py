from datetime import datetime, timezone

from quant.market_state import build_market_state
from quant.models import DataStatus


def test_market_state_is_frozen_semantic_object():
    positioning = {
        "oi": {"total_oi": 1000, "oi_change_total": 25, "count": 4},
        "gex": {
            "status": "ok",
            "net_gex": 12.5,
            "gamma_flip": 4300,
            "call_wall": 4350,
            "put_wall": 4250,
            "calculation_version": "canonical-gex-v1",
            "gex_sign_convention": "DEALER_SHORT_PUBLIC",
            "source_gamma_count": 4,
            "derived_gamma_count": 0,
        },
        "dex": {"status": "ok", "net_dex": 100.0},
        "assumptions": ("dealer_positioning_not_observed",),
    }
    state = build_market_state(
        symbol="GC",
        price=4320,
        as_of=datetime.now(timezone.utc),
        positioning=positioning,
        iv=24.5,
        realized_vol=20.0,
        data_quality=0.95,
        data_status=DataStatus.VALID,
        data_age_seconds=10,
        dataset_version="dataset-test",
    )
    assert state.symbol == "GC"
    assert state.gex == 12.5
    assert state.sign_convention == "DEALER_SHORT_PUBLIC"
    try:
        state.gex = 0
        raise AssertionError("MarketState must be read-only")
    except AttributeError:
        pass
