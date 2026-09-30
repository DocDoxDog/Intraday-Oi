from __future__ import annotations
import hashlib
import os
from datetime import datetime, timezone

from intelligence.customer.api_keys import ApiKeyMaterial, issue_api_key

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

class PostgresApiKeyStore:
    """Issue/revoke API keys without persisting plaintext secrets."""
    def __init__(self, dsn: str | None = None):
        if psycopg is None:
            raise RuntimeError("PSYCOPG_REQUIRED")
        self.dsn = dsn or os.environ.get("SUPABASE_DB_URL")
        if not self.dsn:
            raise RuntimeError("SUPABASE_DB_URL_REQUIRED")

    def create(self, organization_id: str, name: str) -> ApiKeyMaterial:
        material = issue_api_key()
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into commercial.api_keys
                    (organization_id, name, key_prefix, key_hash)
                    values (%s, %s, %s, %s)""",
                    (organization_id, name, material.key_prefix, material.key_hash),
                )
        return material

    def revoke(self, plaintext: str) -> None:
        digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update commercial.api_keys set revoked_at = %s where key_hash = %s and revoked_at is null",
                    (datetime.now(timezone.utc), digest),
                )