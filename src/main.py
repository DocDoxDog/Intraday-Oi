"""
main.py
=======
Orchestrate: scrape -> parse -> analyze -> insert
รันตัวนี้ตัวเดียวพอ (local หรือ GitHub Actions)
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

from scraper import scrape, ScrapeError
from parser import parse, ParseError
from analyze import analyze
from supabase_client import insert_snapshot, upload_screenshot, get_active_chat_ids
import history
import telegram


def run():
    print("[1/7] Scraping QuikStrike...")
    try:
        raw = scrape()
    except ScrapeError as e:
        print(f"❌ Scrape failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/7] Parsing raw data...")
    try:
        parsed = parse(raw)
    except ParseError as e:
        print(f"❌ Parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"    contract={parsed['contract']} future={parsed['future_price']} "
          f"P/C={parsed['put_volume']}/{parsed['call_volume']} dte={parsed.get('dte')}")
    if parsed.get("dte_low_confidence"):
        print("    ⚠️  DTE จับได้จาก fallback pattern เท่านั้น (ไม่เจอ 'vs <price>' ต่อท้าย) "
              "— ค่านี้อาจไม่แม่นยำ ควรเช็คหน้า QuikStrike ว่าโครง heading เปลี่ยนไปหรือไม่",
              file=sys.stderr)

    print("[3/7] Uploading screenshot to Supabase Storage...")
    screenshot_bytes = parsed.pop("screenshot", None)
    screenshot_path = None
    screenshot_url = None
    if screenshot_bytes:
        try:
            uploaded = upload_screenshot(screenshot_bytes, contract=parsed.get("contract"))
            if uploaded:
                screenshot_path = uploaded["path"]
                screenshot_url = uploaded["signed_url"]
            print("    ✅ Screenshot uploaded")
        except Exception as e:
            print(f"⚠️  Screenshot upload failed (continuing without it): {e}", file=sys.stderr)
    else:
        print("    ⚠️  ไม่มี screenshot จากขั้นตอน scrape (ข้ามขั้นตอนนี้)")

    print("[4/7] Fetching history context (hour-ago + today range)...")
    hist_context = history.get_context(contract=parsed.get("contract"))
    hr_ago_status = "พบ" if hist_context.get("hour_ago") else "ไม่พบ"
    today_count = hist_context.get("today", {}).get("count", 0)
    print(f"    hour_ago snapshot: {hr_ago_status} | today snapshots: {today_count}")

    print("[5/7] Analyzing with Gemini...")
    ai_result = analyze(parsed, history=hist_context)
    if "error" in ai_result:
        print(f"⚠️  AI analysis had an issue: {ai_result['error']}")
    else:
        print(f"    market_overview: {ai_result.get('market_overview', '')[:80]}...")

    print("[6/7] Inserting into Supabase...")
    import json
    
    # ⚠️ สกัดข้อมูล dte_low_confidence ทิ้งตรงนี้ เพื่อป้องกันบั๊กเวลาส่งลงฐานข้อมูล
    parsed.pop("dte_low_confidence", None) 
    
    row = insert_snapshot(
        parsed,
        ai_summary=json.dumps(ai_result, ensure_ascii=False),
        screenshot_path=screenshot_path,
        screenshot_url=screenshot_url,
    )
    print(f"✅ Done. Row id={row.get('id')}")

    print("[7/7] Sending to Telegram...")
    # อ่านรายชื่อผู้รับจากตาราง customers ใน Supabase ก่อน (เพิ่ม/ปิดคนได้โดยไม่ต้องแก้ Secret)
    # ถ้ายังไม่ได้รัน migration 005 หรือตารางว่างเปล่า -> fallback ไปใช้ TELEGRAM_CHAT_ID (env) แบบเดิม
    chat_ids = get_active_chat_ids()
    if chat_ids:
        print(f"    ผู้รับจาก Supabase customers table: {len(chat_ids)} คน")
    else:
        print("    ⚠️  ไม่มีรายชื่อใน customers table (หรือยังไม่ได้รัน migration) — fallback ไปใช้ TELEGRAM_CHAT_ID (env)")
        chat_ids = None  # ให้ telegram.send() ไป fallback อ่าน env เอง

    try:
        telegram.send(parsed, ai_result, screenshot_url=screenshot_url, chat_ids=chat_ids)
        print("✅ Sent to Telegram")
    except Exception as e:
        print(f"⚠️  Telegram send failed (data still saved to Supabase): {e}", file=sys.stderr)


if __name__ == "__main__":
    run()
    
