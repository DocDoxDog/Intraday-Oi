"""
supabase_client.py
===================
Insert record ลง table `options_flow_snapshots`
ใช้ service role key เท่านั้น (RLS เปิดอยู่ ไม่มี public policy)
"""

import os
import re
import time
from supabase import create_client, Client

SCREENSHOT_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "oi-screenshots")
# bucket เป็น private — ใช้ signed URL อายุสั้น (แค่พอให้ Telegram ดึงรูปทัน)
# เพราะ CME data ต้องใช้ส่วนตัวเท่านั้น ห้ามเปิด public (ดู README หัวข้อ "ข้อควรระวัง")
SIGNED_URL_EXPIRY_SECONDS = 3600

# Keep the insert compatible with deployments that have the original schema.
# New enrichment fields (spot_price, basis_diff, cfd_price, technical_context)
# remain available to analysis and inside raw_series JSONB, but are not sent as
# top-level columns unless a migration explicitly adds them.
SNAPSHOT_COLUMNS = {
    "captured_at", "contract", "dte", "future_price", "future_chg",
    "put_volume", "call_volume", "vol", "vol_chg", "delta_levels",
    "raw_series", "spot_price", "basis_diff", "cfd_price",
    "price_conversion", "technical_context", "ai_summary",
    "screenshot_path", "screenshot_url",
}


def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def upload_screenshot(image_bytes: bytes | None, contract: str | None = None) -> dict | None:
    """อัปโหลดรูป chart ขึ้น Storage bucket (private) แล้วคืน dict {path, signed_url}
    signed_url หมดอายุใน SIGNED_URL_EXPIRY_SECONDS (พอส่ง Telegram ทัน) แต่ path ไม่หมดอายุ
    เก็บ path ไว้ด้วยเพื่อ regenerate signed url ใหม่ได้ทีหลังตอนอยากดูรูปย้อนหลัง
    ใช้ service role key ซึ่ง bypass RLS อยู่แล้ว ไม่ต้องตั้ง storage policy เพิ่ม"""
    if not image_bytes:
        return None

    client = get_client()
    # Supabase Storage object keys reject/interpret several characters that
    # appear in QuikStrike contract headings: |, ™, %, parentheses and spaces.
    # Keep only portable ASCII key characters; the original contract remains
    # in the database row, so no identifying information is lost.
    safe_contract = re.sub(r"[^A-Za-z0-9._-]+", "_", contract or "unknown")
    safe_contract = re.sub(r"_+", "_", safe_contract).strip("._-") or "unknown"
    path = f"{safe_contract}/{time.strftime('%Y%m%d-%H%M%S')}.png"

    client.storage.from_(SCREENSHOT_BUCKET).upload(
        path, image_bytes, {"content-type": "image/png"}
    )
    signed = client.storage.from_(SCREENSHOT_BUCKET).create_signed_url(
        path, SIGNED_URL_EXPIRY_SECONDS
    )
    signed_url = signed.get("signedURL") or signed.get("signedUrl")
    return {"path": path, "signed_url": signed_url}


def get_signed_url(path: str, expiry_seconds: int = SIGNED_URL_EXPIRY_SECONDS) -> str | None:
    """เรียกใหม่ทีหลังได้ตอนอยากดูรูปย้อนหลัง (signed url เดิมหมดอายุไปแล้ว)"""
    client = get_client()
    signed = client.storage.from_(SCREENSHOT_BUCKET).create_signed_url(path, expiry_seconds)
    return signed.get("signedURL") or signed.get("signedUrl")


def insert_snapshot(
    parsed: dict,
    ai_summary: str | None = None,
    screenshot_path: str | None = None,
    screenshot_url: str | None = None,
) -> dict:
    client = get_client()
    row = {
        **{key: value for key, value in parsed.items() if key in SNAPSHOT_COLUMNS},
        "ai_summary": ai_summary,
        "screenshot_path": screenshot_path,
        "screenshot_url": screenshot_url,
    }
    result = client.table("options_flow_snapshots").insert(row).execute()
    return result.data[0] if result.data else {}


def get_active_chat_ids() -> list[str]:
    """Return active authorized Telegram chat IDs from the customer registry.
    Empty is a valid "nobody authorized" state; registry errors propagate so
    callers cannot mistake an authorization outage for an empty customer list.
    """
    try:
        client = get_client()
        result = (
            client.table("customers")
            .select("chat_id")
            .eq("active", True)
            .execute()
        )
        return [row["chat_id"] for row in (result.data or []) if row.get("chat_id")]
    except Exception as e:
        raise RuntimeError("CUSTOMER_REGISTRY_UNAVAILABLE") from e

def insert_oi_intelligence(parsed: dict, snapshot_id: int | None = None) -> None:
    """Persist structured OI intelligence; service-role only."""
    raw = parsed.get("raw_series") or {}
    client = get_client()
    exposure = raw.get("delta_exposure") or {}
    gex = raw.get("gex") or {}
    base = {
        "snapshot_id": snapshot_id,
        "contract": parsed.get("contract"),
        "dte": parsed.get("dte"),
        "future_price": parsed.get("future_price"),
        "net_delta_exposure": exposure.get("net_delta_exposure"),
        "gross_delta_exposure": exposure.get("gross_delta_exposure"),
        "net_gex": gex.get("net_gex"),
        "call_gex_total": gex.get("call_gex_total"),
        "put_gex_total": gex.get("put_gex_total"),
        "gamma_flip": gex.get("gamma_flip"),
        "call_wall": gex.get("call_wall"),
        "put_wall": gex.get("put_wall"),
        "payload": {"version": raw.get("intelligence_version"), "gex": gex},
    }
    client.table("oi_exposure_snapshots").insert(base).execute()
    events = raw.get("flow_hypotheses", {}).get("events") or []
    if events:
        client.table("oi_flow_events").insert([{
            "snapshot_id": snapshot_id, "contract": parsed.get("contract"), "strike": e.get("strike"),
            "label": e.get("label"), "confidence": e.get("confidence", 0),
            "delta_oi_call": e.get("delta_oi_call"), "delta_oi_put": e.get("delta_oi_put"),
            "evidence": e.get("evidence", []), "limitations": e.get("limitations", []),
        } for e in events]).execute()
    shifts = raw.get("oi_migration", {}).get("shifts") or []
    if shifts:
        client.table("oi_migration_events").insert([{
            "snapshot_id": snapshot_id, "contract": parsed.get("contract"), "side": e.get("side"),
            "from_strike": e.get("from_strike"), "to_strike": e.get("to_strike"),
            "estimated_oi": e.get("estimated_oi"), "confidence": "low",
        } for e in shifts]).execute()
