from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


class PostgresCustomerAccessStore:
    """Direct-Postgres customer authorization for the always-on AWS API."""

    def __init__(self, dsn: str | None = None):
        if psycopg is None:
            raise RuntimeError("PSYCOPG_REQUIRED")
        self.dsn = dsn or os.environ.get("SUPABASE_DB_URL")
        if not self.dsn:
            raise RuntimeError("SUPABASE_DB_URL_REQUIRED")

    def authorize(
        self,
        api_key: str,
        *,
        feature: str,
        symbol: str | None = None,
        now: datetime | None = None,
    ) -> tuple[bool, str | None, str]:
        digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        current = now or datetime.now(timezone.utc)
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select organization_id, revoked_at, expires_at
                    from commercial.api_keys
                    where key_hash = %s
                    limit 1
                    """,
                    (digest,),
                )
                row = cur.fetchone()
                if row is None:
                    return False, None, "API_KEY_INVALID"
                organization_id, revoked_at, expires_at = row
                if revoked_at is not None:
                    return False, str(organization_id), "API_KEY_REVOKED"
                if expires_at is not None and current >= expires_at:
                    return False, str(organization_id), "API_KEY_EXPIRED"

                cur.execute(
                    """
                    select enabled, effective_from, effective_to
                    from commercial.entitlements
                    where organization_id = %s and feature = %s
                    limit 1
                    """,
                    (organization_id, feature),
                )
                ent = cur.fetchone()
                if ent is None:
                    return False, str(organization_id), "ENTITLEMENT_NOT_FOUND"
                enabled, effective_from, effective_to = ent
                if not enabled:
                    return False, str(organization_id), "ENTITLEMENT_DISABLED"
                if effective_from is not None and current < effective_from:
                    return False, str(organization_id), "ENTITLEMENT_NOT_YET_ACTIVE"
                if effective_to is not None and current >= effective_to:
                    return False, str(organization_id), "ENTITLEMENT_EXPIRED"

                if symbol:
                    cur.execute(
                        """
                        select enabled, effective_from, effective_to
                        from commercial.market_access
                        where organization_id = %s and symbol = %s
                        limit 1
                        """,
                        (organization_id, symbol.upper()),
                    )
                    access = cur.fetchone()
                    if access is None or not access[0]:
                        return False, str(organization_id), "MARKET_ACCESS_DENIED"
                    if access[1] is not None and current < access[1]:
                        return False, str(organization_id), "MARKET_ACCESS_NOT_YET_ACTIVE"
                    if access[2] is not None and current >= access[2]:
                        return False, str(organization_id), "MARKET_ACCESS_EXPIRED"

        return True, str(organization_id), "AUTHORIZED"
