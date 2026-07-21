"""
supabase_client.py
===================
Insert record ลง table `options_flow_snapshots`
ใช้ service role key เท่านั้น (RLS เปิดอยู่ ไม่มี public policy)
"""

import os
from supabase import create_client, Client


def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def insert_snapshot(parsed: dict, ai_summary: str | None = None) -> dict:
    client = get_client()
    row = {**parsed, "ai_summary": ai_summary}
    result = client.table("options_flow_snapshots").insert(row).execute()
    return result.data[0] if result.data else {}
