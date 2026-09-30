from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException

from quant.state_store import (
    InMemoryMarketStateRepository,
    MarketStateRecord,
    MarketStateRepository,
    record_to_response,
)
from quant.supabase_repo import SupabaseMarketStateRepository


def _default_repository() -> MarketStateRepository:
    if os.environ.get("CANONICAL_DB_READS", "").lower() == "true":
        return SupabaseMarketStateRepository()
    return InMemoryMarketStateRepository()


def create_app(
    repository: MarketStateRepository | None = None,
    *,
    api_token: str | None = None,
) -> FastAPI:
    repo = repository or _default_repository()
    expected_token = api_token if api_token is not None else os.environ.get("CANONICAL_API_TOKEN")
    app = FastAPI(title="OI Positioning Intelligence API", version="canonical-api-v1")
    app.state.market_state_repository = repo

    def authorize(authorization: str | None) -> None:
        if not expected_token:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="UNAUTHORIZED")
        if authorization[7:].strip() != expected_token:
            raise HTTPException(status_code=403, detail="FORBIDDEN")

    def get_record(symbol: str, authorization: str | None) -> MarketStateRecord:
        authorize(authorization)
        try:
            record = repo.get(symbol.upper())
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "DATA_STORE_UNAVAILABLE", "symbol": symbol.upper()},
            ) from exc
        if record is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "DATA_UNAVAILABLE", "symbol": symbol.upper()},
            )
        return record

    @app.get("/market/{symbol}")
    def market(symbol: str, authorization: str | None = Header(default=None)):
        return record_to_response(get_record(symbol, authorization))

    @app.get("/market/{symbol}/positioning")
    def positioning(symbol: str, authorization: str | None = Header(default=None)):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = payload["data"]["positioning"]
        return payload

    @app.get("/market/{symbol}/oi")
    def oi(symbol: str, authorization: str | None = Header(default=None)):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("oi") or {}
        return payload

    @app.get("/market/{symbol}/gex")
    def gex(symbol: str, authorization: str | None = Header(default=None)):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("gex") or {}
        return payload

    @app.get("/market/{symbol}/expiry")
    def expiry(symbol: str, authorization: str | None = Header(default=None)):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = {
            "expiry_scope": (record.positioning.get("gex") or {}).get("expiry_scope"),
            "oi_by_expiration": (record.positioning.get("oi") or {}).get("oi_by_expiration"),
            "gex_by_expiration": (record.positioning.get("gex") or {}).get("gex_by_expiration"),
            "dex_by_expiration": (record.positioning.get("dex") or {}).get("dex_by_expiration"),
        }
        return payload

    return app


app = create_app()
