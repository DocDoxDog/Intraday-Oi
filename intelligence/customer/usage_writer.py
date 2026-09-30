from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


class PostgresUsageWriter:
    """Server-side usage metering. It records product/API activity only."""

    def __init__(self, dsn: str | None = None):
        if psycopg is None:
            raise RuntimeError("PSYCOPG_REQUIRED")
        self.dsn = dsn or os.environ.get("SUPABASE_DB_URL")
        if not self.dsn:
            raise RuntimeError("SUPABASE_DB_URL_REQUIRED")

    def record(
        self,
        *,
        organization_id: str,
        endpoint: str,
        status_code: int,
        latency_ms: int,
        units: int = 1,
        api_key_id: str | None = None,
    ) -> None:
        occurred_at = datetime.now(timezone.utc)
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into commercial.usage_events
                    (organization_id, api_key_id, endpoint, occurred_at, status_code, latency_ms, units, metadata)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        organization_id,
                        api_key_id,
                        endpoint,
                        occurred_at,
                        status_code,
                        max(0, int(latency_ms)),
                        max(0, int(units)),
                        {"meter_version": "usage-v1"},
                    ),
                )
