from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from quant.state_store import (
    InMemoryMarketStateRepository,
    MarketStateRecord,
    MarketStateRepository,
    record_to_response,
)


def create_app(repository: MarketStateRepository | None = None) -> FastAPI:
    repo = repository or InMemoryMarketStateRepository()
    app = FastAPI(
        title="OI Positioning Intelligence API",
        version="canonical-api-v1",
    )
    app.state.market_state_repository = repo

    def get_record(symbol: str) -> MarketStateRecord:
        record = repo.get(symbol.upper())
        if record is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "DATA_UNAVAILABLE",
                    "symbol": symbol.upper(),
                },
            )
        return record

    @app.get("/market/{symbol}")
    def market(symbol: str, request: Request):
        return record_to_response(get_record(symbol))

    @app.get("/market/{symbol}/positioning")
    def positioning(symbol: str, request: Request):
        record = get_record(symbol)
        payload = record_to_response(record)
        payload["data"] = payload["data"]["positioning"]
        return payload

    @app.get("/market/{symbol}/oi")
    def oi(symbol: str, request: Request):
        record = get_record(symbol)
        payload = record_to_response(record)
        payload["data"] = (record.positioning.get("oi") or {})
        return payload

    @app.get("/market/{symbol}/gex")
    def gex(symbol: str, request: Request):
        record = get_record(symbol)
        payload = record_to_response(record)
        payload["data"] = (record.positioning.get("gex") or {})
        return payload

    @app.get("/market/{symbol}/expiry")
    def expiry(symbol: str, request: Request):
        record = get_record(symbol)
        payload = record_to_response(record)
        payload["data"] = {
            "expiry_scope": (record.positioning.get("gex") or {}).get("expiry_scope"),
            "oi_by_expiration": (record.positioning.get("oi") or {}).get("oi_by_expiration"),
        }
        return payload

    return app


app = create_app()
