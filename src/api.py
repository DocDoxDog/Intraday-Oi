from __future__ import annotations

import os
import time

from fastapi import FastAPI, Header, HTTPException

from intelligence.customer.gateway import CustomerApiRateLimiter
from intelligence.customer.postgres_access import PostgresCustomerAccessStore
from intelligence.customer.supabase_access import SupabaseCustomerAccessStore
from intelligence.customer.usage_writer import PostgresUsageWriter
from intelligence.supabase_reader import SupabaseIntelligenceReader
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
    expected_token = (
        api_token
        if api_token is not None
        else os.environ.get("CANONICAL_API_TOKEN")
    )

    app = FastAPI(
        title="OI Market Intelligence API",
        version="commercial-api-v1",
    )
    app.state.market_state_repository = repo

    customer_rate_limiter = CustomerApiRateLimiter(
        limit=int(os.environ.get("CUSTOMER_API_RATE_LIMIT", "120"))
    )

    intelligence_reader: SupabaseIntelligenceReader | None = None
    customer_access_store = None
    usage_writer = None

    def get_intelligence_reader() -> SupabaseIntelligenceReader:
        nonlocal intelligence_reader
        if intelligence_reader is None:
            intelligence_reader = SupabaseIntelligenceReader()
        return intelligence_reader

    def get_customer_access_store():
        nonlocal customer_access_store
        if customer_access_store is None:
            backend = os.environ.get("CUSTOMER_AUTH_BACKEND", "postgres").lower()
            customer_access_store = (
                PostgresCustomerAccessStore()
                if backend == "postgres"
                else SupabaseCustomerAccessStore()
            )
        return customer_access_store

    def get_usage_writer():
        nonlocal usage_writer
        if usage_writer is None:
            if os.environ.get("CUSTOMER_USAGE_METERING", "true").lower() != "true":
                return None
            try:
                usage_writer = PostgresUsageWriter()
            except Exception:
                usage_writer = False
        return usage_writer

    def meter_customer_request(
        organization_id: str,
        endpoint: str,
        started_at: float,
        status_code: int = 200,
    ) -> None:
        writer = get_usage_writer()
        if not writer:
            return
        try:
            writer.record(
                organization_id=organization_id,
                endpoint=endpoint,
                status_code=status_code,
                latency_ms=max(
                    0, int((time.perf_counter() - started_at) * 1000)
                ),
            )
        except Exception:
            # Usage metering must not change product-data correctness or availability.
            pass

    def authorize(authorization: str | None) -> None:
        if not expected_token:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="UNAUTHORIZED")
        if authorization[7:].strip() != expected_token:
            raise HTTPException(status_code=403, detail="FORBIDDEN")

    def get_record(
        symbol: str,
        authorization: str | None,
    ) -> MarketStateRecord:
        authorize(authorization)
        try:
            record = repo.get(symbol.upper())
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "DATA_STORE_UNAVAILABLE",
                    "symbol": symbol.upper(),
                },
            ) from exc
        if record is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "DATA_UNAVAILABLE",
                    "symbol": symbol.upper(),
                },
            )
        return record

    def get_customer_record(
        symbol: str,
        api_key: str | None,
        feature: str,
    ) -> tuple[MarketStateRecord, str]:
        if os.environ.get("CUSTOMER_API_ENABLED", "").lower() != "true":
            raise HTTPException(status_code=404, detail="CUSTOMER_API_DISABLED")
        if not api_key:
            raise HTTPException(status_code=401, detail="API_KEY_REQUIRED")

        try:
            allowed, organization_id, reason = get_customer_access_store().authorize(
                api_key,
                feature=feature,
                symbol=symbol.upper(),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="CUSTOMER_AUTH_UNAVAILABLE",
            ) from exc

        if not allowed:
            code = 401 if reason == "API_KEY_INVALID" else 403
            raise HTTPException(status_code=code, detail=reason)

        if not organization_id or not customer_rate_limiter.allow(
            organization_id
        ):
            raise HTTPException(status_code=429, detail="API_RATE_LIMITED")

        try:
            record = repo.get(symbol.upper())
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="DATA_STORE_UNAVAILABLE",
            ) from exc

        if record is None:
            raise HTTPException(status_code=503, detail="DATA_UNAVAILABLE")

        return record, str(organization_id)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "oi-market-intelligence"}

    @app.get("/ready")
    def ready():
        if os.environ.get("CANONICAL_DB_READS", "").lower() != "true":
            return {"status": "ready", "canonical_store": "disabled"}

        try:
            record = repo.get(
                os.environ.get("CANONICAL_MARKET_STATE_SYMBOL", "GC").upper()
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="CANONICAL_STORE_UNAVAILABLE",
            ) from exc

        if record is None or record.state.data_status.value != "VALID":
            raise HTTPException(
                status_code=503,
                detail="CANONICAL_DATA_NOT_READY",
            )

        return {
            "status": "ready",
            "canonical_store": "valid",
            "symbol": record.state.symbol,
        }

    @app.get("/metrics")
    def metrics():
        return {
            "service": "oi-market-intelligence",
            "canonical_db_reads": (
                os.environ.get("CANONICAL_DB_READS", "false").lower() == "true"
            ),
            "customer_api_enabled": (
                os.environ.get("CUSTOMER_API_ENABLED", "false").lower() == "true"
            ),
        }

    @app.get("/market/{symbol}")
    def market(
        symbol: str,
        authorization: str | None = Header(default=None),
    ):
        return record_to_response(get_record(symbol, authorization))

    @app.get("/market/{symbol}/positioning")
    def positioning(
        symbol: str,
        authorization: str | None = Header(default=None),
    ):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = payload["data"]["positioning"]
        return payload

    @app.get("/market/{symbol}/oi")
    def oi(
        symbol: str,
        authorization: str | None = Header(default=None),
    ):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("oi") or {}
        return payload

    @app.get("/market/{symbol}/gex")
    def gex(
        symbol: str,
        authorization: str | None = Header(default=None),
    ):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("gex") or {}
        return payload

    @app.get("/market/{symbol}/expiry")
    def expiry(
        symbol: str,
        authorization: str | None = Header(default=None),
    ):
        record = get_record(symbol, authorization)
        payload = record_to_response(record)
        payload["data"] = {
            "expiry_scope": (record.positioning.get("gex") or {}).get(
                "expiry_scope"
            ),
            "oi_by_expiration": (
                record.positioning.get("oi") or {}
            ).get("oi_by_expiration"),
            "gex_by_expiration": (
                record.positioning.get("gex") or {}
            ).get("gex_by_expiration"),
            "dex_by_expiration": (
                record.positioning.get("dex") or {}
            ).get("dex_by_expiration"),
        }
        return payload


    @app.get("/market/{symbol}/news")
    def intelligence_news(symbol: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            data = get_intelligence_reader().news(symbol)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="INTELLIGENCE_DATA_UNAVAILABLE") from exc
        latest = max(data, key=lambda row: str(row.get("published_at") or "")) if data else {}
        return {
            "symbol": symbol.upper(), "as_of": latest.get("published_at") if latest else None,
            "data_age_seconds": None, "data_age": None, "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE", "source": "canonical_intelligence",
            "dataset_version": "mixed", "calculation_version": "mixed", "data": data,
        }

    @app.get("/market/{symbol}/analysis")
    def intelligence_analysis(symbol: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            data = get_intelligence_reader().analyses(symbol)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="INTELLIGENCE_DATA_UNAVAILABLE") from exc
        latest = data[0] if data else {}
        return {
            "symbol": symbol.upper(), "as_of": latest.get("as_of") if latest else None,
            "data_age_seconds": None, "data_age": None, "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE", "source": "canonical_intelligence",
            "dataset_version": latest.get("dataset_version", "unknown") if latest else "unknown",
            "calculation_version": latest.get("calculation_version", "unknown") if latest else "unknown",
            "data": data,
        }

    @app.get("/market/{symbol}/plan")
    def intelligence_plan(symbol: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            data = get_intelligence_reader().plans(symbol)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="INTELLIGENCE_DATA_UNAVAILABLE") from exc
        latest = data[0] if data else {}
        return {
            "symbol": symbol.upper(), "as_of": latest.get("created_at") if latest else None,
            "data_age_seconds": None, "data_age": None, "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE", "source": "canonical_intelligence",
            "dataset_version": "mixed", "calculation_version": "mixed", "data": data,
        }

    @app.get("/api/v1/market/{symbol}")
    def customer_market(
        symbol: str,
        x_api_key: str | None = Header(default=None),
    ):
        started = time.perf_counter()
        record, organization_id = get_customer_record(
            symbol, x_api_key, "market_overview"
        )
        response = record_to_response(record)
        meter_customer_request(
            organization_id,
            f"/api/v1/market/{symbol.upper()}",
            started,
        )
        return response

    @app.get("/api/v1/gex/{symbol}")
    def customer_gex(
        symbol: str,
        x_api_key: str | None = Header(default=None),
    ):
        started = time.perf_counter()
        record, organization_id = get_customer_record(
            symbol, x_api_key, "gex"
        )
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("gex") or {}
        meter_customer_request(
            organization_id,
            f"/api/v1/gex/{symbol.upper()}",
            started,
        )
        return payload

    @app.get("/api/v1/oi/{symbol}")
    def customer_oi(
        symbol: str,
        x_api_key: str | None = Header(default=None),
    ):
        started = time.perf_counter()
        record, organization_id = get_customer_record(
            symbol, x_api_key, "oi"
        )
        payload = record_to_response(record)
        payload["data"] = record.positioning.get("oi") or {}
        meter_customer_request(
            organization_id,
            f"/api/v1/oi/{symbol.upper()}",
            started,
        )
        return payload

    @app.get("/api/v1/positioning/{symbol}")
    def customer_positioning(
        symbol: str,
        x_api_key: str | None = Header(default=None),
    ):
        started = time.perf_counter()
        record, organization_id = get_customer_record(
            symbol, x_api_key, "positioning"
        )
        payload = record_to_response(record)
        payload["data"] = payload["data"]["positioning"]
        meter_customer_request(
            organization_id,
            f"/api/v1/positioning/{symbol.upper()}",
            started,
        )
        return payload

    @app.get("/api/v1/news/{symbol}")
    def customer_news(
        symbol: str,
        x_api_key: str | None = Header(default=None),
    ):
        started = time.perf_counter()
        _record, organization_id = get_customer_record(
            symbol, x_api_key, "news"
        )
        try:
            data = get_intelligence_reader().news(symbol)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="INTELLIGENCE_DATA_UNAVAILABLE",
            ) from exc

        if not data:
            response = {
                "symbol": symbol.upper(),
                "as_of": None,
                "data_age_seconds": None,
                "data_age": None,
                "data_quality": 0.0,
                "data_status": "UNAVAILABLE",
                "source": "canonical_intelligence",
                "dataset_version": "unknown",
                "calculation_version": "unknown",
                "data": [],
            }
        else:
            latest = max(
                data,
                key=lambda row: str(row.get("published_at") or ""),
            )
            response = {
                "symbol": symbol.upper(),
                "as_of": latest.get("published_at"),
                "data_age_seconds": None,
                "data_age": None,
                "data_quality": 1.0,
                "data_status": "VALID",
                "source": "canonical_intelligence",
                "dataset_version": "mixed",
                "calculation_version": "mixed",
                "data": data,
            }

        meter_customer_request(
            organization_id,
            f"/api/v1/news/{symbol.upper()}",
            started,
        )
        return response

    @app.get("/api/v1/analysis/{symbol}")
    def customer_analysis(
        symbol: str,
        x_api_key: str | None = Header(default=None),
    ):
        started = time.perf_counter()
        _record, organization_id = get_customer_record(
            symbol, x_api_key, "analysis"
        )
        try:
            data = get_intelligence_reader().analyses(symbol)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="INTELLIGENCE_DATA_UNAVAILABLE",
            ) from exc

        latest = data[0] if data else {}
        response = {
            "symbol": symbol.upper(),
            "as_of": latest.get("as_of") if latest else None,
            "data_age_seconds": None,
            "data_age": None,
            "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE",
            "source": "canonical_intelligence",
            "dataset_version": latest.get("dataset_version", "unknown"),
            "calculation_version": latest.get(
                "calculation_version", "unknown"
            ),
            "data": data,
        }
        meter_customer_request(
            organization_id,
            f"/api/v1/analysis/{symbol.upper()}",
            started,
        )
        return response

    @app.get("/api/v1/plan/{symbol}")
    def customer_plan(
        symbol: str,
        x_api_key: str | None = Header(default=None),
    ):
        started = time.perf_counter()
        _record, organization_id = get_customer_record(
            symbol, x_api_key, "plan"
        )
        try:
            data = get_intelligence_reader().plans(symbol)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="INTELLIGENCE_DATA_UNAVAILABLE",
            ) from exc

        latest = data[0] if data else {}
        response = {
            "symbol": symbol.upper(),
            "as_of": latest.get("created_at") if latest else None,
            "data_age_seconds": None,
            "data_age": None,
            "data_quality": 1.0 if data else 0.0,
            "data_status": "VALID" if data else "UNAVAILABLE",
            "source": "canonical_intelligence",
            "dataset_version": "mixed",
            "calculation_version": "mixed",
            "data": data,
        }
        meter_customer_request(
            organization_id,
            f"/api/v1/plan/{symbol.upper()}",
            started,
        )
        return response

    return app


app = create_app()
