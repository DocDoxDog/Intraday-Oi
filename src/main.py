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
from supabase_client import insert_snapshot
import telegram


def run():
    print("[1/5] Scraping QuikStrike...")
    try:
        raw = scrape()
    except ScrapeError as e:
        print(f"❌ Scrape failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/5] Parsing raw data...")
    try:
        parsed = parse(raw)
    except ParseError as e:
        print(f"❌ Parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"    contract={parsed['contract']} future={parsed['future_price']} "
          f"P/C={parsed['put_volume']}/{parsed['call_volume']}")

    print("[3/5] Analyzing with Claude...")
    ai_result = analyze(parsed)
    if "error" in ai_result:
        print(f"⚠️  AI analysis had an issue: {ai_result['error']}")
    else:
        print(f"    sentiment={ai_result.get('sentiment')} confidence={ai_result.get('confidence')}")

    print("[4/5] Inserting into Supabase...")
    import json
    row = insert_snapshot(parsed, ai_summary=json.dumps(ai_result, ensure_ascii=False))
    print(f"✅ Done. Row id={row.get('id')}")

    print("[5/5] Sending to Telegram...")
    try:
        telegram.send(parsed, ai_result)
        print("✅ Sent to Telegram")
    except Exception as e:
        # ไม่ทำให้ pipeline ทั้งหมดพัง แค่เพราะส่ง Telegram ไม่สำเร็จ —
        # ข้อมูลถูก insert ลง Supabase ไปแล้ว ยังดึงย้อนดูได้
        print(f"⚠️  Telegram send failed (data still saved to Supabase): {e}", file=sys.stderr)


if __name__ == "__main__":
    run()
