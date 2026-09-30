from __future__ import annotations

import os

from intelligence.customer.subscription import SubscriptionState, features_for_subscription

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

class PostgresEntitlementSync:
    """Synchronize subscription features into server-authoritative entitlements."""
    def __init__(self, dsn: str | None = None):
        if psycopg is None:
            raise RuntimeError("PSYCOPG_REQUIRED")
        self.dsn = dsn or os.environ.get("SUPABASE_DB_URL")
        if not self.dsn:
            raise RuntimeError("SUPABASE_DB_URL_REQUIRED")

    def sync(self, state: SubscriptionState) -> None:
        features = features_for_subscription(state)
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "delete from commercial.entitlements where organization_id = %s",
                    (state.organization_id,),
                )
                for feature in features:
                    cur.execute(
                        """insert into commercial.entitlements
                           (organization_id, feature, enabled, source)
                           values (%s, %s, true, 'subscription')""",
                        (state.organization_id, feature),
                    )