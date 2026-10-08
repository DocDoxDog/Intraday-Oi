"""
supabase_client.py
===================
Insert record ลง table `options_flow_snapshots`
ใช้ service role key เท่านั้น (RLS เปิดอยู่ ไม่มี public policy)
"""

import os
import re
import time
import uuid
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
    "raw_series", "product", "asset_code", "spot_price", "basis_diff", "cfd_price",
    "price_conversion", "technical_context", "ai_summary",
    "screenshot_path", "screenshot_url", "gamma_table_path", "gamma_table_url",
    "gamma_table_full_path", "gamma_table_full_url", "dte_low_cofidence",
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
    # Object keys must be unique across rapid scheduled runs. Second-level
    # timestamps can collide and cause Storage 409s, which would silently drop
    # the real QuikStrike source screenshot from delivery.
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    unique_suffix = uuid.uuid4().hex[:10]
    path = f"{safe_contract}/{timestamp}-{unique_suffix}.png"

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


def upsert_market_bars(technical_context: dict) -> int:
    """Persist Twelve Data OHLCV as point-in-time bars for replay and path analysis."""
    client=get_client()
    rows=[]
    for timeframe,bars in (technical_context.get("ohlcv") or {}).items():
        for bar in bars or []:
            bar_time=bar.get("datetime") or bar.get("bar_time")
            if not bar_time: continue
            rows.append({
                "source":"twelve_data",
                "instrument":technical_context.get("symbol") or "XAU/USD",
                "timeframe":timeframe,
                "bar_time":bar_time,
                "open":bar.get("open"),"high":bar.get("high"),
                "low":bar.get("low"),"close":bar.get("close"),
                "volume":bar.get("volume"),
                "is_final":True,
                "provenance":{"source":"twelve_data","symbol":technical_context.get("symbol") or "XAU/USD"},
            })
    if not rows: return 0
    client.table("market_bars").upsert(rows,on_conflict="source,instrument,timeframe,bar_time").execute()
    return len(rows)


def insert_snapshot(
    parsed: dict,
    ai_summary: str | None = None,
    screenshot_path: str | None = None,
    screenshot_url: str | None = None,
    gamma_table_path: str | None = None,
    gamma_table_url: str | None = None,
    gamma_table_full_path: str | None = None,
    gamma_table_full_url: str | None = None,
) -> dict:
    client = get_client()
    row = {
        **{key: value for key, value in parsed.items() if key in SNAPSHOT_COLUMNS},
        "dte_low_cofidence": parsed.get("dte_low_confidence"),
        "ai_summary": ai_summary,
        "screenshot_path": screenshot_path,
        "screenshot_url": screenshot_url,
        "gamma_table_path": gamma_table_path,
        "gamma_table_url": gamma_table_url,
        "gamma_table_full_path": gamma_table_full_path,
        "gamma_table_full_url": gamma_table_full_url,
    }
    result = client.table("options_flow_snapshots").insert(row).execute()
    return result.data[0] if result.data else {}


def insert_news_announcements(items: list[dict]) -> list[dict]:
    """Upsert news/calendar facts and return only new or materially changed events.

    Economic-calendar rows are mutable: an event is often stored before release
    with no Actual, then the same source row gains Actual after release. Treat
    that transition as an update to the same event instead of creating a
    duplicate announcement.
    """
    if not items:
        return []

    client = get_client()
    normalized_items: list[dict] = []
    for item in items:
        source = str(item.get("source") or "").strip()
        external_id = str(item.get("external_id") or "").strip()
        if source and external_id:
            normalized_items.append(dict(item))
    if not normalized_items:
        return []

    keys = [
        (str(item.get("source") or "").strip(), str(item.get("external_id") or "").strip())
        for item in normalized_items
    ]

    existing_by_key: dict[tuple[str, str], dict] = {}
    for source, external_id in keys:
        result = (
            client.table("news_announcements")
            .select(
                "source,external_id,event_time,actual,forecast,previous,event_status,"
                "calendar_data_status,actual_source,forecast_source,previous_source"
            )
            .eq("source", source)
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            existing_by_key[(source, external_id)] = dict(row)

    persistable_keys = {
        "source",
        "external_id",
        "headline",
        "summary",
        "url",
        "published_at",
        "detected_at",
        "event_time",
        "actual",
        "forecast",
        "previous",
        "event_status",
        "calendar_data_status",
        "actual_source",
        "forecast_source",
        "previous_source",
        "calendar_retrieved_at",
        "category",
        "relevance",
        "rights_status",
    }

    # Build the payload after reading the existing row so a transient provider
    # failure can never erase a previously verified Actual/Forecast/Previous.
    # Calendar facts are monotonic from "unknown" to "known", except when the
    # source explicitly supplies a new non-empty value (e.g. a revision).
    payload: list[dict] = []
    for item in normalized_items:
        key = (
            str(item.get("source") or "").strip(),
            str(item.get("external_id") or "").strip(),
        )
        existing = existing_by_key.get(key) or {}
        merged = {field: item.get(field) for field in persistable_keys if field in item}

        for field in ("actual", "forecast", "previous"):
            incoming = item.get(field)
            previous_value = existing.get(field)
            if incoming in (None, "") and previous_value not in (None, ""):
                merged[field] = previous_value

        for field in ("actual_source", "forecast_source", "previous_source"):
            if not merged.get(field) and existing.get(field):
                merged[field] = existing.get(field)

        if merged.get("event_time") is None and existing.get("event_time") is not None:
            merged["event_time"] = existing.get("event_time")
        if not merged.get("calendar_retrieved_at") and existing.get("calendar_retrieved_at"):
            merged["calendar_retrieved_at"] = existing.get("calendar_retrieved_at")
        if merged.get("calendar_data_status") in (None, "", "UNKNOWN") and existing.get("calendar_data_status"):
            merged["calendar_data_status"] = existing.get("calendar_data_status")

        # Once an event is released, a later feed outage must not downgrade it
        # back to UNKNOWN/UPCOMING.
        effective_actual = merged.get("actual")
        if effective_actual not in (None, ""):
            merged["event_status"] = "RELEASED"
        elif existing.get("event_status") == "RELEASED":
            merged["event_status"] = "RELEASED"
        elif not merged.get("event_status"):
            merged["event_status"] = existing.get("event_status") or "UNKNOWN"

        payload.append(merged)

    # One database write for the batch. The unique(source, external_id)
    # constraint makes this an idempotent event ledger.
    client.table("news_announcements").upsert(
        payload,
        on_conflict="source,external_id",
    ).execute()

    changed: list[dict] = []
    compare_fields = (
        "event_time",
        "actual",
        "forecast",
        "previous",
        "event_status",
        "calendar_data_status",
        "actual_source",
        "forecast_source",
        "previous_source",
    )

    seen_keys: set[tuple[str, str]] = set()
    for item in normalized_items:
        key = (
            str(item.get("source") or "").strip(),
            str(item.get("external_id") or "").strip(),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        previous = existing_by_key.get(key)
        if previous is None or any(
            previous.get(field) != item.get(field)
            for field in compare_fields
        ):
            changed.append(dict(item))

    return changed


def can_notify(channel: str, cooldown_minutes: int = 30) -> tuple[bool, float | None]:
    """Return whether a channel is outside its notification cooldown."""
    channel = str(channel or "").strip().lower()
    if not channel:
        raise ValueError("DELIVERY_CHANNEL_REQUIRED")
    client = get_client()
    result = (
        client.table("bot_delivery_state")
        .select("last_sent_at")
        .eq("channel", channel)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows or not rows[0].get("last_sent_at"):
        return True, None

    from datetime import datetime, timezone
    last = datetime.fromisoformat(
        str(rows[0]["last_sent_at"]).replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    remaining = float(cooldown_minutes * 60) - elapsed
    return remaining <= 0, max(0.0, remaining)


def mark_notified(channel: str) -> None:
    """Record a successful channel delivery timestamp."""
    from datetime import datetime, timezone
    channel = str(channel or "").strip().lower()
    if not channel:
        raise ValueError("DELIVERY_CHANNEL_REQUIRED")
    client = get_client()
    client.table("bot_delivery_state").upsert(
        {
            "channel": channel,
            "last_sent_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="channel",
    ).execute()


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


def insert_multi_expiry_options(parsed: dict, snapshot_id: int | None = None) -> int:
    """Persist normalized multi-expiry observations; missing values remain NULL."""
    snapshots = parsed.get("expiration_snapshots") or []
    if not snapshots:
        return 0

    client = get_client()
    product = str(parsed.get("product_symbol") or "").upper().strip()
    if not product:
        raise RuntimeError("MULTI_EXPIRY_PRODUCT_IDENTITY_UNRESOLVED")
    observed_at = parsed.get("observed_at") or parsed.get("retrieved_at")
    if not observed_at:
        raise RuntimeError("MULTI_EXPIRY_OBSERVED_AT_REQUIRED")

    written = 0
    for item in snapshots:
        raw = item.get("raw_series") or {}
        selection = raw.get("expiration_selection") or {}
        code = item.get("expiration_code") or selection.get("selected")
        if not code:
            raise RuntimeError("MULTI_EXPIRY_EXPIRATION_CODE_REQUIRED")

        expiry_row = {
            "product_symbol": product,
            "expiry_code": str(code),
            "expiry_date": item.get("expiry_date"),
            "observed_at": observed_at,
            "dte": item.get("dte"),
            "source": "cme_quikstrike",
            "source_snapshot_id": snapshot_id,
        }
        expiry_result = (
            client.table("option_expirations")
            .upsert(
                expiry_row,
                on_conflict="product_symbol,expiry_code,observed_at",
            )
            .execute()
        )
        expiry_id = None
        if expiry_result.data:
            expiry_id = expiry_result.data[0].get("id")
        if expiry_id is None:
            lookup = (
                client.table("option_expirations")
                .select("id")
                .eq("product_symbol", product)
                .eq("expiry_code", str(code))
                .eq("observed_at", observed_at)
                .single()
                .execute()
            )
            expiry_id = (lookup.data or {}).get("id")
        if expiry_id is None:
            raise RuntimeError(f"MULTI_EXPIRY_ID_LOOKUP_FAILED:{code}")

        rows = []
        for row in raw.get("strike_rows") or []:
            strike = row.get("strike")
            if not isinstance(strike, (int, float)):
                continue
            rows.append({
                "expiration_id": expiry_id,
                "strike": strike,
                "call_oi": row.get("oiCall"),
                "put_oi": row.get("oiPut"),
                "call_iv": row.get("callIV") if row.get("callIV") is not None else row.get("callImpliedVol"),
                "put_iv": row.get("putIV") if row.get("putIV") is not None else row.get("putImpliedVol"),
                "call_delta": row.get("callDelta"),
                "put_delta": row.get("putDelta"),
                "gamma": row.get("gamma"),
                "call_gex": row.get("call_gex"),
                "put_gex": row.get("put_gex"),
                "net_gex": row.get("net_gex"),
                "observed_at": observed_at,
            })
        if rows:
            client.table("option_strike_observations").upsert(
                rows,
                on_conflict="expiration_id,strike",
            ).execute()
            written += len(rows)

    return written
