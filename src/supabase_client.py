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
from src.event_outcome_engine import HORIZONS_SECONDS, measure_outcome
from supabase import create_client, Client

SCREENSHOT_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "oi-screenshots")
# bucket เป็น private — ใช้ signed URL อายุสั้น (แค่พอให้ Telegram ดึงรูปทัน)
# เพราะ CME data ต้องใช้ส่วนตัวเท่านั้น ห้ามเปิด public (ดู README หัวข้อ "ข้อควรระวัง")
SIGNED_URL_EXPIRY_SECONDS = 3600

def _num(value):
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None

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



def resolve_market_event_outcomes(client=None, instrument: str | None = None) -> int:
    """Fill fixed-horizon outcomes for observed events using stored m5 bars."""
    client = client or get_client()
    query = (
        client.table("market_events")
        .select("id,event_time,detected_at,level,direction,evidence,path_before")
        .eq("status", "OBSERVED")
        .order("event_time", desc=True)
        .limit(100)
    )
    if instrument:
        query = query.eq("instrument", instrument)
    events = query.execute().data or []
    if not events:
        return 0

    bars_query = (
        client.table("market_bars")
        .select("bar_time,open,high,low,close,volume")
        .eq("source", "twelve_data")
        .eq("timeframe", "m5")
        .order("bar_time", desc=False)
        .limit(1000)
    )
    if instrument:
        bars_query = bars_query.eq("instrument", instrument)
    bars = bars_query.execute().data or []
    if not bars:
        return 0

    written = 0
    for event in events:
        path_before = event.get("path_before") or {}
        nodes = path_before.get("nodes") or []
        for horizon in HORIZONS_SECONDS:
            existing = (
                client.table("market_event_outcomes")
                .select("id")
                .eq("event_id", event["id"])
                .eq("horizon_seconds", horizon)
                .limit(1)
                .execute()
            )
            if existing.data:
                continue
            measured = measure_outcome(event, bars, nodes=nodes, horizon_seconds=horizon)
            if measured is None:
                continue
            client.table("market_event_outcomes").insert({
                "event_id": event["id"],
                "horizon_seconds": horizon,
                "observed_at": measured["observed_at"],
                "forward_return": measured["forward_return"],
                "forward_range": measured["forward_range"],
                "mfe": measured["mfe"],
                "mae": measured["mae"],
                "next_node_hit": measured["next_node_hit"],
                "next_node_id": measured["next_node_id"],
                "time_to_next_node_seconds": measured["time_to_next_node_seconds"],
                "outcome_state": measured["outcome_state"],
                "metrics": measured["metrics"],
            }).execute()
            written += 1
    return written


def persist_flow_intelligence(parsed: dict, ai_result: dict, snapshot_id: int | None = None) -> dict:
    """Persist deterministic state/path/event evidence for replay and audit."""
    client = get_client()
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    flow = raw.get("market_flow") or {}
    path = flow.get("path") or ai_result.get("structural_path") or {}
    observed_at = parsed.get("observed_at") or parsed.get("retrieved_at")
    instrument = ((parsed.get("technical_context") or {}).get("symbol") or parsed.get("symbol") or "XAU/USD")

    state_row = {
        "as_of": observed_at,
        "instrument": instrument,
        "state_version": "market-state-v2",
        "regime": state.get("regime"),
        "price_state": state.get("price"),
        "volatility_state": state.get("volatility"),
        "options_state": state.get("gamma"),
        "macro_state": raw.get("macro_state"),
        "technical_state": state.get("technical"),
        "path_state": path,
        "evidence_refs": {"snapshot_id": snapshot_id, "market_flow_version": flow.get("version")},
        "data_quality": {"flow_status": flow.get("status"), "cfd_complete": state.get("cfd_complete")},
    }
    state_result = client.table("market_state_snapshots").insert(state_row).execute()
    state_id = (state_result.data or [{}])[0].get("id")

    node_ids = {}
    nodes = path.get("nodes") or flow.get("nodes") or []
    node_rows = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("level") is None:
            continue
        node_rows.append({
            "snapshot_id": state_id,
            "instrument": instrument,
            "observed_at": observed_at,
            "level": node.get("level"),
            "futures_level": node.get("futures_level"),
            "cfd_level": node.get("level"),
            "node_type": node.get("node_type") or "STRUCTURAL_NODE",
            "role": node.get("role"),
            "tier": node.get("tier"),
            "direction": node.get("direction"),
            "source": node.get("source"),
            "expiry_scope": node.get("expiry_scope"),
            "oi_context": node.get("oi_context"),
            "risk_context": node.get("risk_context"),
            "local_prominence": node.get("local_prominence"),
            "distance_from_price": node.get("distance_from_price"),
            "volatility_distance": node.get("volatility_distance"),
            "state": node.get("state"),
            "evidence_refs": node.get("evidence_refs") or [],
        })
    if node_rows:
        nr = client.table("structural_nodes").insert(node_rows).execute()
        for row, node in zip(nr.data or [], node_rows):
            node_ids[round(float(node["level"]), 5)] = row.get("id")

    transition_rows = []
    for transition in path.get("transitions") or []:
        if not isinstance(transition, dict):
            continue
        from_level = transition.get("from")
        to_level = transition.get("to")
        if from_level in (None, "CURRENT") or to_level in (None, "CURRENT"):
            continue
        from_id = node_ids.get(round(float(from_level), 5)) if _num(from_level) is not None else None
        to_id = node_ids.get(round(float(to_level), 5)) if _num(to_level) is not None else None
        if from_id and to_id:
            transition_rows.append({
                "from_node_id": from_id,
                "to_node_id": to_id,
                "condition_type": transition.get("condition_type") or "UNKNOWN",
                "condition": transition.get("condition") or {},
                "mechanism": transition.get("mechanism"),
                "priority": transition.get("priority"),
                "state": transition.get("state"),
                "evidence_refs": transition.get("evidence_refs") or [],
            })
    if transition_rows:
        client.table("structural_transitions").upsert(
            transition_rows,
            on_conflict="from_node_id,to_node_id,condition_type",
        ).execute()

    event = path.get("observed_last_event") or "NONE"
    event_id = None
    if event != "NONE" and observed_at:
        current = _num(path.get("current_price")) or _num(parsed.get("cfd_price"))
        event_level = _num(path.get("observed_event_level")) or (path.get("upper_node") or path.get("lower_node") or {}).get("level")
        observed_node = path.get("observed_event_node") or {}
        observed_node_level = _num(observed_node.get("level"))
        if event == "BREAK_ACCEPT":
            direction = "UP" if observed_node_level is not None and current is not None and observed_node_level >= current else "DOWN"
        elif event == "RECLAIM":
            direction = "UP" if observed_node_level is not None and current is not None and observed_node_level <= current else "DOWN"
        elif event == "REJECT":
            upper_level = _num((path.get("upper_node") or {}).get("level"))
            lower_level = _num((path.get("lower_node") or {}).get("level"))
            if upper_level is not None and event_level is not None and abs(event_level - upper_level) < 1e-5:
                direction = "DOWN"
            elif lower_level is not None and event_level is not None and abs(event_level - lower_level) < 1e-5:
                direction = "UP"
            else:
                direction = None
        else:
            direction = None

        # Idempotency: the same bar/event/node must not become a new event every
        # scheduler run. A later run can still create a new event after the bar
        # timestamp changes.
        existing = (
            client.table("market_events")
            .select("id")
            .eq("instrument", instrument)
            .eq("event_type", event)
            .eq("event_time", observed_at)
            .eq("source_type", "conditional_path")
            .limit(1)
            .execute()
        )
        if existing.data:
            event_id = existing.data[0].get("id")
        else:
            inserted = client.table("market_events").insert({
                "event_time": observed_at,
                "detected_at": observed_at,
                "instrument": instrument,
                "event_type": event,
                "source_type": "conditional_path",
                "source_ref": str(snapshot_id or state_id or observed_at),
                "level": event_level,
                "direction": direction,
                "magnitude": None,
                "status": "OBSERVED",
                "evidence": {"path": path, "current_price": current},
                "state_before": state,
                "state_after": state,
                "path_before": path,
                "path_after": path,
            }).execute()
            event_id = (inserted.data or [{}])[0].get("id")

    # Resolve older observed events against persisted OHLC bars. Only bars
    # strictly after event_time are eligible, so outcome measurement cannot
    # leak the event bar into the result.
    outcomes_written = resolve_market_event_outcomes(client, instrument=instrument)
    return {
        "state_id": state_id,
        "nodes": len(node_rows),
        "transitions": len(transition_rows),
        "event": event,
        "event_id": event_id,
        "outcomes_written": outcomes_written,
    }

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
