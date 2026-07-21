"""
supabase_client.py
===================
Insert record ลง table `options_flow_snapshots`
ใช้ service role key เท่านั้น (RLS เปิดอยู่ ไม่มี public policy)
"""

import os
import time
from supabase import create_client, Client

SCREENSHOT_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "oi-screenshots")
# bucket เป็น private — ใช้ signed URL อายุสั้น (แค่พอให้ Telegram ดึงรูปทัน)
# เพราะ CME data ต้องใช้ส่วนตัวเท่านั้น ห้ามเปิด public (ดู README หัวข้อ "ข้อควรระวัง")
SIGNED_URL_EXPIRY_SECONDS = 3600


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
    safe_contract = (contract or "unknown").replace("/", "-").replace(" ", "_")
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
        **parsed,
        "ai_summary": ai_summary,
        "screenshot_path": screenshot_path,
        "screenshot_url": screenshot_url,
    }
    result = client.table("options_flow_snapshots").insert(row).execute()
    return result.data[0] if result.data else {}
