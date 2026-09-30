from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client

from quant.serialization import to_jsonable
from quant.state_store import MarketStateRecord


class SupabaseMarketStateWriter:
    """Server-side writer for the canonical MarketState store."""

    TABLE = "oi_core_market_states"

    def __init__(
        self,
        *,
        url: str | None = None,
        service_role_key: str | None = None,
        client: Client | None = None,
    ) -> None:
        if client is not None:
            self.client = client
            return
        db_url = url or os.environ.get("SUPABASE_URL")
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not db_url or not key:
            raise RuntimeError("SUPABASE_SERVER_CREDENTIALS_MISSING")
        self.client = create_client(db_url, key)

    def put(self, record: MarketStateRecord) -> None:
        state = record.state
        row: dict[str, Any] = {
            "symbol": state.symbol,
            "as_of": state.as_of.isoformat(),
            "price": state.price,
            "oi": state.oi,
            "oi_change": state.oi_change,
            "gex": state.gex,
            "dex": state.dex,
            "iv": state.iv,
            "realized_vol": state.realized_vol,
            "gamma_flip": state.gamma_flip,
            "call_wall": state.call_wall,
            "put_wall": state.put_wall,
            "positioning_regime": state.positioning_regime,
            "volatility_regime": state.volatility_regime,
            "data_quality": state.data_quality,
            "data_age_seconds": state.data_age_seconds,
            "data_status": state.data_status.value,
            "dataset_version": state.dataset_version,
            "calculation_version": state.calculation_version,
            "sign_convention": state.sign_convention,
            "gamma_source": state.gamma_source,
            "assumptions": list(state.assumptions),
            "evidence": list(state.evidence),
            "positioning": to_jsonable(record.positioning),
        }
        self.client.table(self.TABLE).insert(row).execute()
