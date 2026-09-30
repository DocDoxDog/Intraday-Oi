from __future__ import annotations

import os

from supabase import Client, create_client

from quant.models import DataStatus, MarketState
from quant.state_store import MarketStateRecord


class SupabaseMarketStateRepository:
    """Read-only canonical MarketState repository.

    Service-role access is server-side only. The adapter never calculates OI/GEX.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        service_role_key: str | None = None,
        client: Client | None = None,
    ):
        if client is not None:
            self.client = client
            return

        db_url = url or os.environ.get("SUPABASE_URL")
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not db_url or not key:
            raise RuntimeError("SUPABASE_SERVER_CREDENTIALS_MISSING")
        self.client = create_client(db_url, key)

    def get(self, symbol: str) -> MarketStateRecord | None:
        result = (
            self.client.table("market_states")
            .select("*")
            .eq("symbol", symbol.upper())
            .order("as_of", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None

        row = result.data[0]
        state = MarketState(
            symbol=row["symbol"],
            price=row.get("price"),
            as_of=__import__("datetime").datetime.fromisoformat(
                str(row["as_of"]).replace("Z", "+00:00")
            ),
            oi=row.get("oi"),
            oi_change=row.get("oi_change"),
            gex=row.get("gex"),
            dex=row.get("dex"),
            iv=row.get("iv"),
            realized_vol=row.get("realized_vol"),
            gamma_flip=row.get("gamma_flip"),
            call_wall=row.get("call_wall"),
            put_wall=row.get("put_wall"),
            positioning_regime=row.get("positioning_regime") or "UNKNOWN",
            volatility_regime=row.get("volatility_regime") or "UNKNOWN",
            data_quality=float(row.get("data_quality") or 0.0),
            data_age_seconds=row.get("data_age_seconds"),
            data_status=DataStatus(row.get("data_status") or "UNAVAILABLE"),
            dataset_version=row.get("dataset_version") or "unknown",
            calculation_version=row.get("calculation_version") or "unknown",
            sign_convention=row.get("sign_convention"),
            gamma_source=row.get("gamma_source"),
            assumptions=tuple(row.get("assumptions") or []),
            evidence=tuple(row.get("evidence") or []),
        )
        return MarketStateRecord(
            state=state,
            positioning=row.get("positioning") or {},
        )
