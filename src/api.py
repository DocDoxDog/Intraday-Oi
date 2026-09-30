from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException

from intelligence.customer.gateway import CustomerApiRateLimiter
from intelligence.supabase_reader import SupabaseIntelligenceReader
from intelligence.customer.supabase_access import SupabaseCustomerAccessStore
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
    customer_rate_limiter = CustomerApiRateLimiter(
        limit=int(os.environ.get("CUSTOMER_API_RATE_LIMIT", "120"))
    )
    intelligence_reader = SupabaseIntelligenceReader()

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


    @app.get("/health")
    def health():
        return {"status": "ok", "service": "oi-market-intelligence"}

    @app.get("/ready")
    def ready():
        if os.environ.get("CANONICAL_DB_READS", "").lower() != "true":
            return {"status": "ready", "canonical_store": "disabled"}
        try:
            record = repo.get(os.environ.get("CANONICAL_MARKET_STATE_SYMBOL", "GC").upper())
        except Exception as exc:
            raise HTTPException(status_code=503, detail="CANONICAL_STORE_UNAVAILABLE") from exc
        if record is None or record.state.data_status.value != "VALID":
            raise HTTPException(status_code=503, detail="CANONICAL_DATA_NOT_READY")
        return {"status": "ready", "canonical_store": "valid", "symbol": record.state.symbol}

    @app.get("/metrics")
    def metrics():
        return {
            "service": "oi-market-intelligence",
            "canonical_db_reads": os.environ.get("CANONICAL_DB_READS", "false").lower() == "true",
        }

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


    def get_customer_record(symbol: str, api_key: str | None, feature: str) -> MarketStateRecord:
        if os.environ.get("CUSTOMER_API_ENABLED", "").lower() != "true":
            raise HTTPException(status_code=404, detail="CUSTOMER_API_DISABLED")
        if not api_key:
            raise HTTPException(status_code=401, detail="API_KEY_REQUIRED")
        try:
            allowed, organization_id, reason = SupabaseCustomerAccessStore().authorize(
                api_key, feature=feature, symbol=symbol.upper()
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="CUSTOMER_AUTH_UNAVAILABLE") from exc
        if not allowed:
            code = 403 if reason not in {"API_KEY_INVALID"} else 401
            raise HTTPException(status_code=code, detail=reason)
        if not organization_id or not customer_rate_limiter.allow(organization_id):
            raise HTTPException(status_code=429, detail="API_RATE_LIMITED")
        try:
            record = repo.get(symbol.upper())
        except Exception as exc:
            raise HTTPException(status_code=503, detail="DATA_STORE_UNAVAILABLE") from exc
        if record is None:
            raise HTTPException(status_code=503, detail="DATA_UNAVAILABLE")
        return record

    @app.get("/api/v1/market/{symbol}")
    def customer_market(symbol: str, x_api_key: str | None = Header(default=None)):
        record = get_customer_record(symbol, x_api_key, "market_overview")
        return record_to_response(record)

    @app.get("/api/v1/gex/{symbol}")
    def customer_gex(symbol: str, x_api_key: str | None = Header(default=None)):
        record = get_customer_record(symbol, x_api_key, "gex")
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("gex") or {}
        return payload

    @app.get("/api/v1/oi/{symbol}")
    def customer_oi(symbol: str, x_api_key: str | None = Header(default=None)):
        record = get_customer_record(symbol, x_api_key, "oi")
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("oi") or {}
        return payload

    @app.get("/api/v1/positioning/{symbol}")
    def customer_positioning(symbol: str, x_api_key: str | None = Header(default=None)):
        record = get_customer_record(symbol, x_api_key, "positioning")
        payload = record_to_response(record)
        payload["data"] = payload["data"]["positioning"]
        return payload


    @app.get("/api/v1/news/{symbol}")
    def customer_news(symbol: str, x_api_key: str | None = Header(default=None)):
        get_customer_record(symbol, x_api_key, "news")
        try:
            data = intelligence_reader.news(symbol)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="INTELLIGENCE_DATA_UNAVAILABLE") from exc
        return {
            "symbol": symbol.upper(), "as_of": None, "data_age_seconds": None,
            "data_age": None, "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE",
            "source": "canonical_intelligence",
            "dataset_version": "mixed", "calculation_version": "mixed",
            "data": data,
        }

    @app.get("/api/v1/analysis/{symbol}")
    def customer_analysis(symbol: str, x_api_key: str | None = Header(default=None)):
        get_customer_record(symbol, x_api_key, "analysis")
        try:
            data = intelligence_reader.analyses(symbol)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="INTELLIGENCE_DATA_UNAVAILABLE") from exc
        return {
            "symbol": symbol.upper(), "as_of": data[0].get("as_of") if data else None,
            "data_age_seconds": None, "data_age": None,
            "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE",
            "source": "canonical_intelligence",
            "dataset_version": data[0].get("dataset_version", "unknown") if data else "unknown",
            "calculation_version": data[0].get("calculation_version", "unknown") if data else "unknown",
            "data": data,
        }

    @app.get("/api/v1/plan/{symbol}")
    def customer_plan(symbol: str, x_api_key: str | None = Header(default=None)):
        get_customer_record(symbol, x_api_key, "plan")
        try:
            data = intelligence_reader.plans(symbol)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="INTELLIGENCE_DATA_UNAVAILABLE") from exc
        return {
            "symbol": symbol.upper(), "as_of": data[0].get("created_at") if data else None,
            "data_age_seconds": None, "data_age": None,
            "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE",
            "source": "canonical_intelligence",
            "dataset_version": "mixed", "calculation_version": "mixed",
            "data": data,
        }

    return app


app = create_app()
