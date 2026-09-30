from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client


class SupabaseIntelligenceReader:
    """Server-side read adapter for public canonical intelligence tables."""

    def __init__(self, *, client: Client | None = None, url: str | None = None, service_role_key: str | None = None):
        if client is not None:
            self.client = client
            return
        db_url = url or os.environ.get("SUPABASE_URL")
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not db_url or not key:
            raise RuntimeError("SUPABASE_SERVER_CREDENTIALS_MISSING")
        self.client = create_client(db_url, key)

    def news(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        result = (
            self.client.table("oi_core_news_items")
            .select("*")
            .contains("assets", [symbol.upper()])
            .order("published_at", desc=True)
            .limit(min(max(limit, 1), 100))
            .execute()
        )
        return list(result.data or [])

    def analyses(self, symbol: str, limit: int = 10) -> list[dict[str, Any]]:
        result = (
            self.client.table("oi_core_market_analyses")
            .select("*")
            .eq("symbol", symbol.upper())
            .order("as_of", desc=True)
            .limit(min(max(limit, 1), 50))
            .execute()
        )
        return list(result.data or [])

    def plans(self, symbol: str, limit: int = 10) -> list[dict[str, Any]]:
        result = (
            self.client.table("oi_core_scenario_plans")
            .select("*")
            .eq("market", symbol.upper())
            .order("created_at", desc=True)
            .limit(min(max(limit, 1), 50))
            .execute()
        )
        return list(result.data or [])
