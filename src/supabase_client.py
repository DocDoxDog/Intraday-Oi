import os
import time
from supabase import create_client, Client

SCREENSHOT_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "oi-screenshots")
SIGNED_URL_EXPIRY_SECONDS = 3600


def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def upload_screenshot(image_bytes: bytes | None, contract: str | None = None) -> dict | None:
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


def get_active_chat_ids() -> list[str]:
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
        print(f"⚠️  ดึงรายชื่อ customers จาก Supabase ไม่สำเร็จ: {e}")
        return []