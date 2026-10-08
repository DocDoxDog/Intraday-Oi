from datetime import datetime, timezone, timedelta

from src.canonical_options import (
    CANONICAL_VERSION,
    GEX_MODEL_VERSION,
    build_canonical_snapshot,
    expiry_weight,
    freshness_status,
    validate_canonical_snapshot,
)


def test_freshness_marks_old_oi_stale():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=3)).isoformat()
    assert freshness_status(old, now=now, max_age_seconds=172800) == "STALE"


def test_expiry_weight_is_bounded_and_near_expiry_is_stronger():
    assert 0 < expiry_weight(1) <= 1
    assert expiry_weight(1) > expiry_weight(30)


def test_canonical_contract_preserves_unknowns_and_provenance():
    observed = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "contract": "GC",
        "observed_at": observed,
        "dte": 3.2,
        "raw_series": {
            "expiration_selection": {"selected": "OGZ26"},
            "strike_rows": [
                {
                    "strike": 4200,
                    "oiCall": 100,
                    "oiPut": None,
                    "oi_delta_call": 5,
                    "vol": 18.5,
                    "callDelta": 0.5,
                    "putDelta": None,
                    "net_gex": 1234,
                }
            ],
            "gex": {
                "status": "ok",
                "net_gex": 1234,
                "model": "dealer_short_all",
                "model_version": GEX_MODEL_VERSION,
            },
        },
    }
    state = build_canonical_snapshot(snapshot)
    assert state["contract_version"] == CANONICAL_VERSION
    assert state["expiration"]["code"] == "OGZ26"
    assert state["expiration"]["expiry_weight"] is not None
    assert state["levels"][0]["put_oi"] is None
    assert state["gex"]["model_version"] == GEX_MODEL_VERSION
    assert validate_canonical_snapshot(state) == []
