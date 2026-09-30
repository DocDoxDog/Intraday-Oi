from datetime import datetime, timezone

from fastapi.testclient import TestClient

from quant.models import DataStatus
from quant.market_state import build_market_state
from quant.state_store import InMemoryMarketStateRepository, MarketStateRecord
from src.api import create_app


def make_repo():
    repo = InMemoryMarketStateRepository()
    state = build_market_state(
        symbol="GC",
        price=4300.0,
        as_of=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
        positioning={
            "oi": {"count": 2, "total_oi": 1000, "oi_change_total": 10, "oi_by_expiration": {"exp-1": 1000}},
            "gex": {
                "status": "ok",
                "net_gex": 12.5,
                "gamma_flip": 4280,
                "call_wall": 4350,
                "put_wall": 4250,
                "expiry_scope": "ALL_ACTIVE",
                "calculation_version": "canonical-gex-v1",
                "gex_sign_convention": "DEALER_SHORT_PUBLIC",
                "source_gamma_count": 2,
                "derived_gamma_count": 0,
                "gex_by_expiration": {"exp-1": {"net_gex": 12.5}},
            },
            "dex": {"status": "ok", "net_dex": 40, "dex_by_expiration": {"exp-1": {"net_dex": 40}}},
            "assumptions": ("dealer_positioning_not_observed",),
        },
        iv=22,
        realized_vol=18,
        data_quality=0.95,
        data_status=DataStatus.VALID,
        data_age_seconds=4,
        dataset_version="dataset-test",
    )
    repo.put(MarketStateRecord(state, {
        "oi": {"count": 2, "total_oi": 1000, "oi_change_total": 10, "oi_by_expiration": {"exp-1": 1000}},
        "gex": {"status": "ok", "net_gex": 12.5, "gamma_flip": 4280, "call_wall": 4350, "put_wall": 4250, "expiry_scope": "ALL_ACTIVE", "gex_by_expiration": {"exp-1": {"net_gex": 12.5}}},
        "dex": {"status": "ok", "net_dex": 40, "dex_by_expiration": {"exp-1": {"net_dex": 40}}},
    }))
    return repo


def test_market_envelope_contains_versions_and_quality():
    client = TestClient(create_app(make_repo()))
    response = client.get("/market/GC")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "GC"
    assert body["data_age_seconds"] == 4
    assert body["data_quality"] == 0.95
    assert body["dataset_version"] == "dataset-test"
    assert body["calculation_version"] == "canonical-gex-v1"


def test_subresources_use_canonical_values():
    client = TestClient(create_app(make_repo()))
    assert client.get("/market/GC/gex").json()["data"]["net_gex"] == 12.5
    assert client.get("/market/GC/oi").json()["data"]["total_oi"] == 1000
    expiry = client.get("/market/GC/expiry").json()["data"]
    assert expiry["gex_by_expiration"]["exp-1"]["net_gex"] == 12.5
    assert expiry["dex_by_expiration"]["exp-1"]["net_dex"] == 40


def test_auth_blocks_when_configured():
    client = TestClient(create_app(make_repo(), api_token="secret"))
    assert client.get("/market/GC").status_code == 401
    assert client.get("/market/GC", headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert client.get("/market/GC", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_missing_symbol_is_data_unavailable():
    client = TestClient(create_app())
    response = client.get("/market/SI")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DATA_UNAVAILABLE"
