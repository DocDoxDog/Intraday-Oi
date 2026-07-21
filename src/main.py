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
from supabase_client import insert_snapshot, upload_screenshot
import telegram


def run():
    print("[1/6] Scraping QuikStrike...")
    try:
        raw = scrape()
    except ScrapeError as e:
        print(f"❌ Scrape failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/6] Parsing raw data...")
    try:
        parsed = parse(raw)
    except ParseError as e:
        print(f"❌ Parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"    contract={parsed['contract']} future={parsed['future_price']} "
          f"P/C={parsed['put_volume']}/{parsed['call_volume']}")

    print("[3/6] Analyzing with Gemini...")
    ai_result = analyze(parsed)
    if "error" in ai_result:
        print(f"⚠️  AI analysis had an issue: {ai_result['error']}")
    else:
        print(f"    market_overview: {ai_result.get('market_overview', '')[:80]}...")

    print("[4/6] Uploading screenshot to Supabase Storage...")
    screenshot_bytes = parsed.pop("screenshot", None)  # ไม่ใช่ jsonb column ต้องแยกออกก่อน insert
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
            # แคปรูปไม่สำเร็จไม่ควรทำให้ pipeline ทั้งหมดพัง — ตัวเลขวิเคราะห์สำคัญกว่า
            print(f"⚠️  Screenshot upload failed (continuing without it): {e}", file=sys.stderr)
    else:
        print("    ⚠️  ไม่มี screenshot จากขั้นตอน scrape (ข้ามขั้นตอนนี้)")

    print("[5/6] Inserting into Supabase...")
    import json
    row = insert_snapshot(
        parsed,
        ai_summary=json.dumps(ai_result, ensure_ascii=False),
        screenshot_path=screenshot_path,
        screenshot_url=screenshot_url,
    )
    print(f"✅ Done. Row id={row.get('id')}")

    print("[6/6] Sending to Telegram...")
    try:
        telegram.send(parsed, ai_result, screenshot_url=screenshot_url)
        print("✅ Sent to Telegram")
    except Exception as e:
        # ไม่ทำให้ pipeline ทั้งหมดพัง แค่เพราะส่ง Telegram ไม่สำเร็จ —
        # ข้อมูลถูก insert ลง Supabase ไปแล้ว ยังดึงย้อนดูได้
        print(f"⚠️  Telegram send failed (data still saved to Supabase): {e}", file=sys.stderr)


if __name__ == "__main__":
    run()
