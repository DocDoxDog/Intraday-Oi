"""
history.py
===========
ดึงข้อมูลย้อนหลังจาก Supabase table `options_flow_snapshots` มาเสริม context ให้ analyze.py
เพื่อให้ AI เห็น "เทรนด์" ไม่ใช่แค่ตัดขวางเวลาเดียว

ดึง 2 ก้อน:
1. hour_ago  -> record ที่ใกล้เคียง 1 ชม.ก่อนที่สุด (สำหรับเทียบ Vol Chg / P-C shift ระยะสั้น)
2. today     -> ทุก record ของ "วันนี้" (ตามเวลากรุงเทพ) สรุปเป็น range/trend สั้นๆ ไม่ส่งดิบทั้งหมด
                (กัน prompt ยาวเกินไปและกัน noise จาก raw_series ที่หนัก)
"""

import os
import re
from datetime import datetime, timezone, timedelta
try:
    from .supabase_client import get_client
except ImportError:
    from supabase_client import get_client

BANGKOK_TZ = timezone(timedelta(hours=7))

# ฟิลด์ที่ดึงมาใช้จริง — ไม่ดึง raw_series/screenshot_url เพราะหนักและไม่จำเป็นสำหรับ trend summary
FIELDS = "captured_at,contract,dte,future_price,future_chg,put_volume,call_volume,vol,vol_chg,raw_series"


def _history_contract_prefix(contract: str | None) -> str | None:
    """Normalize QuikStrike's changing heading into a stable series identity."""
    if not contract:
        return None
    text = str(contract).strip()
    match = re.match(
        r"^(?P<prefix>.*?\b[A-Za-z0-9._-]+)\s*\([0-9]+(?:\.[0-9]+)?\s*DTE\)",
        text,
        re.I,
    )
    return match.group("prefix").strip() if match else text


def _apply_series_filter(query, contract: str | None):
    prefix = _history_contract_prefix(contract)
    if prefix:
        return query.ilike("contract", prefix + "%")
    return query


def _bangkok_day_bounds(now: datetime | None = None) -> tuple[str, str]:
    now = (now or datetime.now(timezone.utc)).astimezone(BANGKOK_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def get_hour_ago_snapshot(contract: str | None = None) -> dict | None:
    """หา record ที่ใกล้เคียง 1 ชม.ก่อนที่สุด (ภายในหน้าต่าง 45-90 นาทีก่อน กันกรณีไม่มีรอบตรงเป๊ะ)"""
    client = get_client()
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(minutes=90)).isoformat()
    window_end = (now - timedelta(minutes=45)).isoformat()

    query = (
        client.table("options_flow_snapshots")
        .select(FIELDS)
        .gte("captured_at", window_start)
        .lte("captured_at", window_end)
        .order("captured_at", desc=True)
        .limit(1)
    )
    query = _apply_series_filter(query, contract)

    result = query.execute()
    return result.data[0] if result.data else None


def _compact_raw_summary(raw: dict) -> dict:
    totals = raw.get("totals") or {}
    gex = raw.get("gex") or {}
    return {
        "oi_put": totals.get("open_interest_view_put", totals.get("open_interest_put")),
        "oi_call": totals.get("open_interest_view_call", totals.get("open_interest_call")),
        "oi_total": totals.get("open_interest_view_total", totals.get("open_interest_total")),
        "oi_change_put": totals.get("oi_delta_put", totals.get("oi_change_put")),
        "oi_change_call": totals.get("oi_delta_call", totals.get("oi_change_call")),
        "oi_change_total": totals.get("oi_delta_total"),
        "churn": totals.get("churn"),
        "quikstrike_churn_put": totals.get("quikstrike_churn_put"),
        "quikstrike_churn_call": totals.get("quikstrike_churn_call"),
        "gex_net": gex.get("net_gex"),
        "gamma_flip": gex.get("gamma_flip"),
        "call_wall": gex.get("call_wall"),
        "put_wall": gex.get("put_wall"),
    }


def _summary_for_range(rows: list[dict]) -> dict:
    if not rows:
        return {"count": 0}

    future_prices = [float(r["future_price"]) for r in rows if r.get("future_price") is not None]
    vols = [float(r["vol"]) for r in rows if r.get("vol") is not None]
    chg = [float(r["future_chg"]) for r in rows if r.get("future_chg") is not None]
    vol_chg = [float(r["vol_chg"]) for r in rows if r.get("vol_chg") is not None]

    def last(field):
        vals = [r.get(field) for r in rows if r.get(field) is not None]
        return vals[-1] if vals else None

    first_raw = (rows[0].get("raw_series") or {})
    last_raw = (rows[-1].get("raw_series") or {})
    last_totals = _compact_raw_summary(last_raw)
    first_totals = _compact_raw_summary(first_raw)

    return {
        "count": len(rows),
        "first_snapshot_time": rows[0].get("captured_at"),
        "latest_snapshot_time": rows[-1].get("captured_at"),
        "future_price_open": future_prices[0] if future_prices else None,
        "future_price_high": max(future_prices) if future_prices else None,
        "future_price_low": min(future_prices) if future_prices else None,
        "future_price_last": future_prices[-1] if future_prices else None,
        "future_change_last": last("future_chg"),
        "future_change_min": min(chg) if chg else None,
        "future_change_max": max(chg) if chg else None,
        "vol_min": min(vols) if vols else None,
        "vol_max": max(vols) if vols else None,
        "vol_first": vols[0] if vols else None,
        "vol_last": vols[-1] if vols else None,
        "vol_change_last": last("vol_chg"),
        "oi_first": first_totals,
        "oi_last": last_totals,
    }


def get_today_summary(contract: str | None = None) -> dict:
    """สรุปทั้งวันตามเวลา Bangkok โดยส่งเฉพาะ compact metrics ให้ LLM."""
    client = get_client()
    start_iso, end_iso = _bangkok_day_bounds()

    query = (
        client.table("options_flow_snapshots")
        .select(FIELDS)
        .gte("captured_at", start_iso)
        .lte("captured_at", end_iso)
        .order("captured_at", desc=False)
    )
    query = _apply_series_filter(query, contract)

    rows = query.execute().data or []
    return _summary_for_range(rows)


def get_yesterday_summary(contract: str | None = None) -> dict:
    """สรุปวันก่อนหน้าตามเวลา Bangkok เพื่อใช้เป็นบริบทเทียบวันต่อวัน."""
    client = get_client()
    now = datetime.now(timezone.utc).astimezone(BANGKOK_TZ)
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)

    query = (
        client.table("options_flow_snapshots")
        .select(FIELDS)
        .gte("captured_at", start.astimezone(timezone.utc).isoformat())
        .lt("captured_at", end.astimezone(timezone.utc).isoformat())
        .order("captured_at", desc=False)
    )
    query = _apply_series_filter(query, contract)

    rows = query.execute().data or []
    return _summary_for_range(rows)


def get_oi_baseline(contract: str | None = None) -> dict | None:
    """Return the latest snapshot before today's Bangkok session as EOD baseline."""
    client = get_client()
    start_iso, _ = _bangkok_day_bounds()
    query = (client.table("options_flow_snapshots").select("captured_at,contract,raw_series")
             .lt("captured_at", start_iso)
             .order("captured_at", desc=True).limit(1))
    # QuikStrike headings contain the current expiration/DTE, so exact contract
    # equality makes the EOD baseline disappear when the expiration changes.
    query = _apply_series_filter(query, contract)
    result = query.execute()
    return result.data[0] if result.data else None


def get_context(contract: str | None = None) -> dict:
    """เรียกใช้ตัวเดียวจาก main.py — คืนทั้งสองก้อนพร้อม fail-safe
    ถ้า query history พังไม่ควรทำให้ pipeline หลักล่ม แค่ analyze แบบไม่มี context ย้อนหลัง"""
    try:
        hour_ago = get_hour_ago_snapshot(contract)
    except Exception as e:
        hour_ago = None
        print(f"⚠️  ดึง hour_ago snapshot ไม่สำเร็จ: {e}")

    try:
        today = get_today_summary(contract)
    except Exception as e:
        today = {"count": 0}
        print(f"⚠️  ดึง today summary ไม่สำเร็จ: {e}")

    try:
        yesterday = get_yesterday_summary(contract)
    except Exception as e:
        yesterday = {"count": 0}
        print(f"⚠️  ดึง yesterday summary ไม่สำเร็จ: {e}")

    try:
        oi_baseline = get_oi_baseline(contract)
    except Exception as e:
        oi_baseline = None
        print(f"⚠️  ดึง OI baseline ไม่สำเร็จ: {e}")

    return {"hour_ago": hour_ago, "today": today, "yesterday": yesterday, "oi_baseline": oi_baseline}
