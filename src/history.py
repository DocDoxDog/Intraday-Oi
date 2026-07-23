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
from datetime import datetime, timezone, timedelta
from supabase_client import get_client

BANGKOK_TZ = timezone(timedelta(hours=7))

# ฟิลด์ที่ดึงมาใช้จริง — ไม่ดึง raw_series/screenshot_url เพราะหนักและไม่จำเป็นสำหรับ trend summary
FIELDS = "captured_at,contract,dte,future_price,future_chg,put_volume,call_volume,vol,vol_chg,delta_levels"


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
    if contract:
        query = query.eq("contract", contract)

    result = query.execute()
    return result.data[0] if result.data else None


def get_today_summary(contract: str | None = None) -> dict:
    """สรุป range ของวันนี้ (ตามเวลากรุงเทพ) — ไม่ส่งข้อมูลดิบทั้งหมดเข้า prompt
    ส่งแค่ min/max/count + จุดแรก-จุดล่าสุด พอให้ AI เห็นทิศทางของทั้งวัน"""
    client = get_client()
    start_iso, end_iso = _bangkok_day_bounds()

    query = (
        client.table("options_flow_snapshots")
        .select(FIELDS)
        .gte("captured_at", start_iso)
        .lte("captured_at", end_iso)
        .order("captured_at", desc=False)
    )
    if contract:
        query = query.eq("contract", contract)

    rows = query.execute().data or []
    if not rows:
        return {"count": 0}

    pc_ratios = [
        r["put_volume"] / r["call_volume"]
        for r in rows
        if r.get("put_volume") and r.get("call_volume")
    ]
    future_prices = [r["future_price"] for r in rows if r.get("future_price") is not None]
    vols = [r["vol"] for r in rows if r.get("vol") is not None]

    return {
        "count": len(rows),
        "first_snapshot_time": rows[0]["captured_at"],
        "latest_snapshot_time": rows[-1]["captured_at"],
        "future_price_open": future_prices[0] if future_prices else None,
        "future_price_high": max(future_prices) if future_prices else None,
        "future_price_low": min(future_prices) if future_prices else None,
        "pc_ratio_min": round(min(pc_ratios), 2) if pc_ratios else None,
        "pc_ratio_max": round(max(pc_ratios), 2) if pc_ratios else None,
        "vol_min": min(vols) if vols else None,
        "vol_max": max(vols) if vols else None,
    }


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

    return {"hour_ago": hour_ago, "today": today}
