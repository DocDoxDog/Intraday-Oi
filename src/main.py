"""
main.py
=======
Orchestrate: scrape -> parse -> analyze -> insert
รันตัวนี้ตัวเดียวพอ (local หรือ GitHub Actions)
"""

import sys
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

import sys
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# Always import Intraday-Oi as a package so the same code path works in
# GitHub Actions (python -m src.main) and direct local execution (python src/main.py).
if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scraper import scrape, scrape_multi_expiration, ScrapeError
from src.parser import parse, ParseError
from src.analyze import analyze
from src.twelve_data import fetch_spot, enrich_with_basis, TwelveDataError
from src.technical_analysis import build_context
from src.oi_positioning import enrich as enrich_oi_positioning
from src.supabase_client import insert_snapshot, insert_oi_intelligence, insert_multi_expiry_options, upload_screenshot, get_active_chat_ids
from src.url_manager import UrlManager, UrlManagerError
from src import history, telegram, line
from src.multi_expiry import build_gamma_matrix, summarize_gamma_zones
from src.gamma_chart import render_gamma_table


def run():
    print("[1/9] Resolving QuikStrike URL (self-healing)...")
    try:
        url_manager = UrlManager()
        quikstrike_url = url_manager.get_url()
    except UrlManagerError as e:
        print(f"❌ URL resolution failed completely: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/9] Scraping QuikStrike...")
    try:
        max_expirations = max(1, int(os.environ.get("QUIKSTRIKE_MAX_EXPIRATIONS", "7")))
        if max_expirations > 1:
            raw = scrape_multi_expiration(quikstrike_url, limit=max_expirations)
            print(f"    multi-expiration enabled: {len(raw.get('expiration_snapshots') or [])} expirations")
        else:
            raw = scrape(quikstrike_url)
    except (ScrapeError, ValueError) as e:
        print(f"❌ Scrape failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("[3/9] Parsing raw data...")
    try:
        parsed = parse(raw)
    except ParseError as e:
        print(f"❌ Parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    parsed.setdefault("product_symbol", "GC")
    parsed["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    parsed["observed_at"] = parsed["retrieved_at"]
    expiry_snapshots = parsed.get("expiration_snapshots") or []
    if expiry_snapshots:
        gamma_matrix = build_gamma_matrix(expiry_snapshots, current_price=parsed.get("future_price"))
        gamma_zones = summarize_gamma_zones(gamma_matrix)
        parsed.setdefault("raw_series", {})["multi_expiry_gamma"] = gamma_matrix
        parsed["raw_series"]["multi_expiry_gamma_zones"] = gamma_zones
        print(f"    gamma matrix: {gamma_matrix['expiration_count']} expirations x {len(gamma_matrix['strikes'])} strikes")
    print(f"    product={parsed['product_symbol']} contract={parsed['contract']} future={parsed['future_price']} "
          f"dte={parsed.get('dte')} retrieved_at={parsed['retrieved_at']}")
    if parsed.get("dte_low_confidence"):
        print("    ⚠️  DTE จับได้จาก fallback pattern เท่านั้น (ไม่เจอ 'vs <price>' ต่อท้าย) "
              "— ค่านี้อาจไม่แม่นยำ ควรเช็คหน้า QuikStrike ว่าโครง heading เปลี่ยนไปหรือไม่",
              file=sys.stderr)

    print("[3.5/9] Fetching XAU/USD spot and converting Futures levels to CFD...")
    if os.environ.get("TWELVEDATA_API_KEY"):
        try:
            spot_data = fetch_spot()
            enrich_with_basis(parsed, spot_data)
            print(
                f"    spot={parsed['spot_price']} diff={parsed['basis_diff']} "
                f"cfd={parsed['cfd_price']}"
            )
        except TwelveDataError as e:
            print(f"⚠️  Twelve Data enrichment failed (keeping Futures levels): {e}", file=sys.stderr)
    else:
        print("    ⏭️  ข้าม Twelve Data (ไม่ได้ตั้งค่า TWELVEDATA_API_KEY)")

    print("[3.7/9] Building hidden multi-timeframe technical confirmation...")
    if os.environ.get("TWELVEDATA_API_KEY"):
        try:
            parsed["technical_context"] = build_context()
            confirmation = parsed["technical_context"].get("confirmation", {})
            print(
                f"    bias={confirmation.get('bias')} "
                f"htf_aligned={confirmation.get('htf_aligned')}"
            )
        except Exception as e:
            print(f"⚠️  Technical confirmation failed (AI will use Options data only): {e}", file=sys.stderr)
    else:
        print("    ⏭️  ข้าม technical confirmation (ไม่มี Twelve Data key)")

    print("[4/9] Uploading Gamma Table + OI screenshot to Supabase Storage...")
    screenshot_bytes = parsed.pop("screenshot", None)
    screenshot_path = None
    screenshot_url = None
    gamma_table_path = None
    gamma_table_url = None

    gamma_matrix = (parsed.get("raw_series") or {}).get("multi_expiry_gamma")
    if gamma_matrix and gamma_matrix.get("status") == "VALID":
        try:
            gamma_bytes = render_gamma_table(gamma_matrix)
            uploaded_gamma = upload_screenshot(gamma_bytes, contract=f"{parsed.get('contract')}_GAMMA_TABLE")
            if uploaded_gamma:
                gamma_table_path = uploaded_gamma["path"]
                gamma_table_url = uploaded_gamma["signed_url"]
            print("    ✅ Gamma Table uploaded")
        except Exception as e:
            print(f"⚠️  Gamma Table upload failed (continuing): {e}", file=sys.stderr)
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

    print("[5/9] Fetching history context (hour-ago + today range)...")
    hist_context = history.get_context(contract=parsed.get("contract"))
    hr_ago_status = "พบ" if hist_context.get("hour_ago") else "ไม่พบ"
    today_count = hist_context.get("today", {}).get("count", 0)
    print(f"    hour_ago snapshot: {hr_ago_status} | today snapshots: {today_count}")
    parsed = enrich_oi_positioning(parsed, hist_context.get("oi_baseline"))
    oi_totals = (parsed.get("raw_series") or {}).get("totals") or {}
    print(
        f"    OI positioning baseline={'yes' if oi_totals.get('oi_baseline_available') else 'no'} "
        f"ΔOI put={oi_totals.get('oi_delta_put', 0)} call={oi_totals.get('oi_delta_call', 0)}"
    )

    print("[5.5/9] Building deterministic OI intelligence...")
    try:
        from src.oi_intelligence import enrich as enrich_oi_intelligence
        previous = hist_context.get("hour_ago")
        parsed = enrich_oi_intelligence(parsed, previous)
        intel = (parsed.get("raw_series") or {})
        dex = intel.get("delta_exposure") or {}
        flow = intel.get("flow_hypotheses") or {}
        migration = intel.get("oi_migration") or {}
        def _fmt_num(value):
            return f"{value:,.0f}" if isinstance(value, (int, float)) else "UNKNOWN"
        def _fmt_pct(value):
            return f"{value:.0%}" if isinstance(value, (int, float)) else "UNKNOWN"
        print(f"    net_delta={_fmt_num(dex.get('net_delta_exposure'))} "
              f"gross_delta={_fmt_num(dex.get('gross_delta_exposure'))} "
              f"flow_unknown={_fmt_pct(flow.get('unknown_rate'))} "
              f"migrations={len(migration.get('shifts', []))}")
    except Exception as e:
        print(f"⚠️  OI intelligence failed (raw OI remains available): {e}", file=sys.stderr)

    print("[6/9] Running local supaBOT-compatible analyst core → Gemini...")
    try:
        ai_result = analyze(parsed, history=hist_context)
    except Exception as e:
        # กันไว้อีกชั้น เผื่อ analyze.py มี unexpected error ที่ไม่ใช่ RequestException
        # (เช่น bug ใหม่ในอนาคต) — ไม่ให้ข้อมูลที่ scrape มาดีๆ เสียทิ้งทั้งรอบ
        print(f"⚠️  Unexpected error in analyze() (continuing to save raw data): {e}", file=sys.stderr)
        ai_result = {"error": f"Unexpected exception: {e}"}

    if "error" in ai_result:
        print(f"⚠️  AI analysis had an issue: {ai_result['error']}")
    else:
        print(f"    market_overview: {ai_result.get('market_overview', '')[:80]}...")

    ai_failed = "error" in ai_result
    if ai_failed:
        raw = parsed.get("raw_series") or {}
        gex = raw.get("gex") or {}
        gamma = raw.get("multi_expiry_gamma") or {}
        zones = raw.get("multi_expiry_gamma_zones") or {}
        ai_result = {
            "analysis_status": "DEGRADED",
            "market_overview": "รอบนี้ไม่มีผลจาก LLM ที่ผ่าน verification จึงแสดงเฉพาะ deterministic market state",
            "what": "ระบบยืนยันได้เฉพาะข้อมูล QuikStrike/OI/GEX ที่เก็บได้ในรอบนี้",
            "why": "ไม่มี analyst output ที่ผ่าน JSON/schema/verifier จึงไม่ควรสรุปทิศทางแทนโมเดล",
            "positioning": (
                f"GEX call wall={gex.get('call_wall') or 'UNKNOWN'} | "
                f"put wall={gex.get('put_wall') or 'UNKNOWN'} | "
                f"multi-expiry={gamma.get('expiration_count') or 0}"
            ),
            "levels": {
                "resistance_far": None,
                "resistance_main": gex.get("call_wall"),
                "resistance_current": None,
                "support_current": None,
                "support_main": gex.get("put_wall"),
                "support_deep": None,
            },
            "scenarios": {
                "bull": "รอ confirmation จาก price/technical evidence",
                "bear": "รอ confirmation จาก price/technical evidence",
                "sideway": "ข้อมูลยังไม่พอสำหรับยืนยัน scenario",
            },
            "bias": "WAIT",
            "uncertainty": 1.0,
            "trade_plan": {
                "status": "NO_TRADE",
                "setup": "ยังไม่เปิด setup เพราะ analyst output ไม่ผ่าน verification",
                "confirmation": "ต้องมี analyst output + technical confirmation ที่ผ่าน gate",
                "invalidation": "ยังไม่มี setup ที่อนุมัติ",
                "risk_note": "ห้ามสร้าง Entry/SL/TP จาก OI เพียงอย่างเดียว",
            },
            "data_limitations": [
                "LLM output rejected before delivery: " + str(ai_result.get("error")),
                "ไม่มี news evidence ในรอบนี้",
            ],
            "evidence_refs": ["itb:oi:deterministic"],
        }
        print("    ⚠️ ใช้ DEGRADED V2: ไม่สร้าง bias/levels/trade plan จากข้อมูลที่ไม่มีหลักฐาน")

    print("[7/9] Inserting into Supabase...")
    import json
    
    # ⚠️ สกัดข้อมูล dte_low_confidence ทิ้งตรงนี้ เพื่อป้องกันบั๊กเวลาส่งลงฐานข้อมูล
    parsed.pop("dte_low_confidence", None) 
    row = insert_snapshot(
        parsed,
        ai_summary=json.dumps(ai_result, ensure_ascii=False),
        screenshot_path=screenshot_path,
        screenshot_url=screenshot_url,
        gamma_table_path=gamma_table_path,
        gamma_table_url=gamma_table_url,
    )
    print(f"✅ Done. Row id={row.get('id')}")
    try:
        insert_oi_intelligence(parsed, snapshot_id=row.get("id"))
        print("    ✅ Structured OI intelligence persisted")
    except Exception as e:
        print(f"⚠️  Structured OI persistence failed (snapshot remains saved): {e}", file=sys.stderr)

    if parsed.get("expiration_snapshots"):
        try:
            written = insert_multi_expiry_options(parsed, snapshot_id=row.get("id"))
            print(f"    ✅ Multi-expiry option observations persisted: {written} rows")
        except Exception as e:
            print(f"⚠️  Multi-expiry persistence failed (snapshot remains saved): {e}", file=sys.stderr)

    print("[8/9] Sending to Telegram...")
    # Authorization is fail-closed: Supabase customer registry is the source of truth.
    # Never fall back to TELEGRAM_CHAT_ID, because an unavailable/empty registry
    # must not become an authorization bypass.
    try:
        chat_ids = get_active_chat_ids()
    except Exception as e:
        print(f"    ❌ Telegram authorization registry unavailable: {e}", file=sys.stderr)
        chat_ids = []
    if chat_ids:
        print(f"    ผู้รับจาก Supabase customers table: {len(chat_ids)} คน")
    else:
        print("    ⏭️  ไม่มีผู้รับที่ active ใน Supabase customers — ข้าม Telegram", file=sys.stderr)
        chat_ids = []

    try:
        telegram.send(parsed, ai_result, screenshot_url=screenshot_url, gamma_table_url=gamma_table_url, chat_ids=chat_ids)
        print("✅ Sent to Telegram")
    except Exception as e:
        print(f"⚠️  Telegram send failed (data still saved to Supabase): {e}", file=sys.stderr)

    print("[9/9] Sending to LINE (broadcast to all OA friends)...")
    if os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"):
        try:
            line.send(parsed, ai_result, screenshot_url=screenshot_url)
            print("✅ Sent to LINE")
        except Exception as e:
            print(f"⚠️  LINE send failed (data still saved to Supabase): {e}", file=sys.stderr)
    else:
        print("    ⏭️  ข้าม LINE (ไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN)")


if __name__ == "__main__":
    run()
