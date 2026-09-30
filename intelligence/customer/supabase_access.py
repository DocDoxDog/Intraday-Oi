from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any

from supabase import Client, create_client


class SupabaseCustomerAccessStore:
    """Read-only customer authorization backed by the commercial schema."""

    def __init__(self, *, client: Client | None = None, url: str | None = None, service_role_key: str | None = None):
        if client is not None:
            self.client = client
            return
        db_url = url or os.environ.get("SUPABASE_URL")
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not db_url or not key:
            raise RuntimeError("SUPABASE_SERVER_CREDENTIALS_MISSING")
        self.client = create_client(db_url, key)

    def authorize(
        self,
        api_key: str,
        *,
        feature: str,
        symbol: str | None = None,
        now: datetime | None = None,
    ) -> tuple[bool, str | None, str]:
        digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        key_result = (
            self.client.table("commercial.api_keys")
            .select("id,organization_id,key_hash,revoked_at,expires_at")
            .eq("key_hash", digest)
            .limit(1)
            .execute()
        )
        if not key_result.data:
            return False, None, "API_KEY_INVALID"
        row = key_result.data[0]
        if row.get("revoked_at"):
            return False, row.get("organization_id"), "API_KEY_REVOKED"
        if row.get("expires_at"):
            expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            current = now or datetime.now(expires.tzinfo)
            if current >= expires:
                return False, row.get("organization_id"), "API_KEY_EXPIRED"

        entitlement = (
            self.client.table("commercial.entitlements")
            .select("enabled,effective_from,effective_to")
            .eq("organization_id", row["organization_id"])
            .eq("feature", feature)
            .limit(1)
            .execute()
        )
        if not entitlement.data:
            return False, row["organization_id"], "ENTITLEMENT_NOT_FOUND"
        ent = entitlement.data[0]
        if not bool(ent.get("enabled")):
            return False, row["organization_id"], "ENTITLEMENT_DISABLED"

        current = now or datetime.now(datetime.fromisoformat(str(row.get("expires_at") or "2099-01-01T00:00:00+00:00").replace("Z", "+00:00")).tzinfo)
        if ent.get("effective_from") and current < datetime.fromisoformat(str(ent["effective_from"]).replace("Z", "+00:00")):
            return False, row["organization_id"], "ENTITLEMENT_NOT_YET_ACTIVE"
        if ent.get("effective_to") and current >= datetime.fromisoformat(str(ent["effective_to"]).replace("Z", "+00:00")):
            return False, row["organization_id"], "ENTITLEMENT_EXPIRED"

        if symbol:
            access = (
                self.client.table("commercial.market_access")
                .select("enabled,effective_from,effective_to")
                .eq("organization_id", row["organization_id"])
                .eq("symbol", symbol.upper())
                .limit(1)
                .execute()
            )
            if not access.data or not bool(access.data[0].get("enabled")):
                return False, row["organization_id"], "MARKET_ACCESS_DENIED"

        return True, row["organization_id"], "AUTHORIZED"
