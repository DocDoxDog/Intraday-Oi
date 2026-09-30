from __future__ import annotations
import os

from intelligence.alert_service import AlertDeliveryRecord

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

class PostgresAlertRepository:
    """Persistent alert/story delivery state for dedupe and message editing."""
    def __init__(self, dsn: str | None = None):
        if psycopg is None:
            raise RuntimeError("PSYCOPG_REQUIRED")
        self.dsn = dsn or os.environ.get("SUPABASE_DB_URL")
        if not self.dsn:
            raise RuntimeError("SUPABASE_DB_URL_REQUIRED")

    def find_story(self, organization_id: str, story_cluster_id: str):
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """select id, organization_id, story_cluster_id, 'TELEGRAM',
                              telegram_chat_id, telegram_message_id, version, status, updated_at
                       from commercial.alerts
                       where organization_id = %s and story_cluster_id = %s
                         and status in ('SENT','EDITED')
                       order by updated_at desc limit 1""",
                    (organization_id, story_cluster_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return AlertDeliveryRecord(
                    alert_id=str(row[0]), organization_id=str(row[1]),
                    story_cluster_id=str(row[2]), channel=str(row[3]),
                    destination=str(row[4] or ""),
                    provider_message_id=str(row[5]) if row[5] is not None else None,
                    version=int(row[6]), status=str(row[7]), updated_at=row[8],
                )

    def create(self, record: AlertDeliveryRecord) -> None:
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into commercial.alerts
                       (id, organization_id, story_cluster_id, alert_type, severity, dedupe_key,
                        status, telegram_chat_id, telegram_message_id, version, created_at, updated_at)
                       values (%s,%s,%s,'NEWS','MEDIUM',%s,%s,%s,%s,%s,%s,%s)""",
                    (record.alert_id, record.organization_id, record.story_cluster_id,
                     "story:" + record.story_cluster_id, record.status, record.destination,
                     record.provider_message_id, record.version, record.updated_at, record.updated_at),
                )

    def update(self, record: AlertDeliveryRecord) -> None:
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """update commercial.alerts
                       set telegram_chat_id=%s, telegram_message_id=%s, version=%s,
                           status=%s, updated_at=%s
                       where id=%s and organization_id=%s""",
                    (record.destination, record.provider_message_id, record.version,
                     record.status, record.updated_at, record.alert_id, record.organization_id),
                )