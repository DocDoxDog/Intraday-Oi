from __future__ import annotations

from datetime import datetime, timezone

from quant.models import DataStatus, MarketState
from quant.state_store import MarketStateRecord, record_from_payload
from quant.raw import RawMarketData, sanitize_payload
from quant.supabase_writer import SupabaseMarketStateWriter, SupabaseRawMarketDataWriter


class FakeTable:
    def __init__(self):
        self.inserted = None

    def insert(self, row):
        self.inserted = row
        return self

    def execute(self):
        return type("Result", (), {"data": [self.inserted]})()


class FakeClient:
    def __init__(self):
        self.table_obj = FakeTable()

    def table(self, name):
        assert name == "oi_core_market_states"
        return self.table_obj


def make_record():
    state = MarketState(
        symbol="GC",
        price=3825.5,
        as_of=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        oi=12345.0,
        oi_change=25.0,
        gex=1000.0,
        dex=250.0,
        iv=18.2,
        realized_vol=None,
        gamma_flip=3820.0,
        call_wall=3850.0,
        put_wall=3800.0,
        positioning_regime="UNKNOWN",
        volatility_regime="UNKNOWN",
        data_quality=1.0,
        data_age_seconds=0.0,
        data_status=DataStatus.VALID,
        dataset_version="fixture:v1",
        calculation_version="canonical-gex-v1",
        sign_convention="DEALER_SHORT_PUBLIC",
        gamma_source="quikstrike",
        assumptions=("dealer_positioning_not_observed",),
        evidence=("GEX_STATUS:ok",),
    )
    return MarketStateRecord(state=state, positioning={"gex": {"net_gex": 1000.0}})


def test_writer_rejects_incomplete_state():
    import pytest
    record = make_record()
    state = MarketState(**{**record.state.__dict__, "data_status": DataStatus.INCOMPLETE})
    incomplete = MarketStateRecord(state=state, positioning=record.positioning)
    with pytest.raises(RuntimeError, match="CANONICAL_STATE_NOT_ELIGIBLE"):
        SupabaseMarketStateWriter(client=FakeClient()).put(incomplete)


def test_writer_inserts_canonical_state():
    client = FakeClient()
    SupabaseMarketStateWriter(client=client).put(make_record())
    row = client.table_obj.inserted
    assert row["symbol"] == "GC"
    assert row["data_status"] == "VALID"
    assert row["dataset_version"] == "fixture:v1"
    assert row["positioning"]["gex"]["net_gex"] == 1000.0


def test_record_payload_rehydration_does_not_change_values():
    original = make_record()
    payload = {
        "symbol": original.state.symbol,
        "price": original.state.price,
        "as_of": original.state.as_of.isoformat(),
        "oi": original.state.oi,
        "oi_change": original.state.oi_change,
        "gex": original.state.gex,
        "dex": original.state.dex,
        "iv": original.state.iv,
        "realized_vol": original.state.realized_vol,
        "gamma_flip": original.state.gamma_flip,
        "call_wall": original.state.call_wall,
        "put_wall": original.state.put_wall,
        "positioning_regime": original.state.positioning_regime,
        "volatility_regime": original.state.volatility_regime,
        "data_quality": original.state.data_quality,
        "data_age_seconds": original.state.data_age_seconds,
        "data_status": original.state.data_status.value,
        "dataset_version": original.state.dataset_version,
        "calculation_version": original.state.calculation_version,
        "sign_convention": original.state.sign_convention,
        "gamma_source": original.state.gamma_source,
        "assumptions": list(original.state.assumptions),
        "evidence": list(original.state.evidence),
    }
    restored = record_from_payload(payload, original.positioning)
    assert restored.state == original.state
    assert restored.positioning == original.positioning


def test_raw_writer_persists_dataset_version_and_payload():
    class FakeUpsert:
        def __init__(self, table):
            self.table = table
            self.row = None
        def upsert(self, row, on_conflict=None):
            self.row = row
            assert on_conflict == "version"
            return self
        def insert(self, row):
            self.row = row
            return self
        def execute(self):
            return type("Result", (), {"data": [self.row]})()

    class RawClient:
        def __init__(self):
            self.tables = {}
        def table(self, name):
            self.tables.setdefault(name, FakeUpsert(name))
            return self.tables[name]

    payload = sanitize_payload({"strike": 3800, "screenshot": b"abc"})
    raw = RawMarketData.create(
        source="quikstrike", payload=payload, source_version="legacy-v1",
        fetched_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    client = RawClient()
    SupabaseRawMarketDataWriter(client=client).put(raw)
    assert client.tables["oi_core_dataset_versions"].row["version"] == raw.dataset_version
    assert client.tables["oi_core_raw_market_data"].row["checksum"] == raw.checksum
    assert client.tables["oi_core_raw_market_data"].row["payload"]["screenshot"]["__binary__"] is True
