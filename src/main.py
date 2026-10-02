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
from src.supabase_client import (
    insert_snapshot,
    insert_oi_intelligence,
    insert_multi_expiry_options,
    upload_screenshot,
    get_active_chat_ids,
    insert_news_announcements,
)
from src.url_manager import UrlManager, UrlManagerError
from src import history, telegram, line
from src.multi_expiry import build_gamma_matrix, summarize_gamma_zones, merge_expected_expirations, build_gold_weekly_series_window
from src.gamma_chart import render_gamma_table, render_gamma_table_full
from src.news_announcement import collect_news, format_news_announcement
from src.market_state import enrich_market_state, normalize_analyst_output


def run():
    # Cron (:20/:50) is the scheduler. Workflow concurrency prevents overlap.
    # bot_delivery_state is reserved for delivery state, not job scheduling.

    print("[1/9] Resolving QuikStrike URL (self-healing)...")
    try:
        url_manager = UrlManager()
        quikstrike_url = url_manager.get_url()
    except UrlManagerError as e:
        print(f"❌ URL resolution failed completely: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/9] Scraping QuikStrike...")
    try:
        max_expirations = max(1, int(os.environ.get("QUIKSTRIKE_MAX_EXPIRATIONS", "12")))
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

    parsed["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    parsed["observed_at"] = parsed["retrieved_at"]
    expiry_snapshots = parsed.get("expiration_snapshots") or []
    if expiry_snapshots:
        gamma_matrix = build_gamma_matrix(expiry_snapshots, current_price=parsed.get("future_price"))
        gamma_matrix = merge_expected_expirations(
            gamma_matrix,
            as_of=parsed.get("observed_at"),
            count=max(7, int(os.environ.get("QUIKSTRIKE_DISPLAY_EXPIRATIONS", "7"))),
        )
        gamma_zones = summarize_gamma_zones(gamma_matrix)
        parsed.setdefault("raw_series", {})["multi_expiry_gamma"] = gamma_matrix
        parsed["raw_series"]["multi_expiry_gamma_zones"] = gamma_zones
        parsed["raw_series"]["gold_series_window"] = build_gold_weekly_series_window(
            as_of=parsed.get("observed_at"),
            count=max(7, int(os.environ.get("QUIKSTRIKE_DISPLAY_EXPIRATIONS", "7"))),
        )
        observed_columns = sum(1 for c in gamma_matrix["columns"] if c.get("status") == "OBSERVED")
        print(
            f"    gamma matrix: {len(gamma_matrix['columns'])} display expirations "
            f"(observed {observed_columns}) x {len(gamma_matrix['strikes'])} strikes"
        )
    print(f"    product={parsed.get('product_symbol') or 'UNKNOWN'} contract={parsed['contract']} future={parsed['future_price']} "
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
            print(f"⚠️  Twelve Data enrichment failed; CFD/Basis remain UNKNOWN and CFD levels will not be fabricated: {e}", file=sys.stderr)
    else:
        print("    ⏭️  ข้าม Twelve Data (ไม่ได้ตั้งค่า TWELVEDATA_API_KEY) — CFD/Basis remain UNKNOWN")

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
    gamma_table_full_path = None
    gamma_table_full_url = None

    gamma_matrix = (parsed.get("raw_series") or {}).get("multi_expiry_gamma")
    if gamma_matrix and gamma_matrix.get("status") == "VALID":
        try:
            gamma_bytes = render_gamma_table(gamma_matrix)
            uploaded_gamma = upload_screenshot(
                gamma_bytes, contract=f"{parsed.get('contract')}_GAMMA_COMPACT"
            )
            if uploaded_gamma:
                gamma_table_path = uploaded_gamma["path"]
                gamma_table_url = uploaded_gamma["signed_url"]

            full_bytes = render_gamma_table_full(gamma_matrix)
            uploaded_full = upload_screenshot(
                full_bytes, contract=f"{parsed.get('contract')}_GAMMA_FULL"
            )
            if uploaded_full:
                gamma_table_full_path = uploaded_full["path"]
                gamma_table_full_url = uploaded_full["signed_url"]
            print("    ✅ Gamma Table compact + full uploaded")
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

    print("[5/9] Fetching history context (1H + 2H + today + yesterday)...")
    hist_context = history.get_context(contract=parsed.get("contract"))
    hr_ago_status = "พบ" if hist_context.get("hour_ago") else "ไม่พบ"
    two_hr_status = "พบ" if hist_context.get("two_hours_ago") else "ไม่พบ"
    today_count = hist_context.get("today", {}).get("count", 0)
    yesterday_count = hist_context.get("yesterday", {}).get("count", 0)
    print(f"    1H: {hr_ago_status} | 2H: {two_hr_status} | today snapshots: {today_count} | yesterday snapshots: {yesterday_count}")
    parsed = enrich_oi_positioning(parsed, hist_context.get("oi_baseline"))
    oi_totals = (parsed.get("raw_series") or {}).get("totals") or {}
    print(
        f"    OI positioning baseline={'yes' if oi_totals.get('oi_baseline_available') else 'no'} "
        f"ΔOI put={oi_totals.get('oi_delta_put') if oi_totals.get('oi_delta_put') is not None else 'UNKNOWN'} "
        f"call={oi_totals.get('oi_delta_call') if oi_totals.get('oi_delta_call') is not None else 'UNKNOWN'}"
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

    # Deterministic cross-session deltas used by the renderer and LLM.
    try:
        raw_intel = parsed.setdefault("raw_series", {})
        cur_totals = raw_intel.get("totals") or {}
        cur_gex = raw_intel.get("gex") or {}
        cur_price = parsed.get("future_price")
        cur_vol = parsed.get("vol")
        def _num(v):
            return float(v) if isinstance(v, (int, float)) else None
        today = hist_context.get("today") or {}
        yesterday = hist_context.get("yesterday") or {}
        today_open = today.get("future_price_open")
        today_oi = today.get("oi_first") or {}
        today_gex = today_oi.get("gex_net")
        yesterday_last = yesterday.get("future_price_last")
        yesterday_oi = yesterday.get("oi_last") or {}
        yesterday_gex = yesterday_oi.get("gex_net")
        current_oi_total = _num(cur_totals.get("open_interest_view_total", cur_totals.get("open_interest_total")))
        current_oi_put = _num(cur_totals.get("open_interest_view_put", cur_totals.get("open_interest_put")))
        current_oi_call = _num(cur_totals.get("open_interest_view_call", cur_totals.get("open_interest_call")))
        raw_intel["history_comparison"] = {
            "today_price_change": _num(cur_price) - _num(today_open) if _num(cur_price) is not None and _num(today_open) is not None else None,
            "today_oi_change": current_oi_total - _num(today_oi.get("oi_total")) if current_oi_total is not None and _num(today_oi.get("oi_total")) is not None else None,
            "today_gex_change": _num(cur_gex.get("net_gex")) - _num(today_gex) if _num(cur_gex.get("net_gex")) is not None and _num(today_gex) is not None else None,
            "yesterday_price_change": _num(cur_price) - _num(yesterday_last) if _num(cur_price) is not None and _num(yesterday_last) is not None else None,
            "yesterday_oi_change": current_oi_total - _num(yesterday_oi.get("oi_total")) if current_oi_total is not None and _num(yesterday_oi.get("oi_total")) is not None else None,
            "yesterday_gex_change": _num(cur_gex.get("net_gex")) - _num(yesterday_gex) if _num(cur_gex.get("net_gex")) is not None and _num(yesterday_gex) is not None else None,
            "today_count": today.get("count", 0),
            "yesterday_count": yesterday.get("count", 0),
        }
    except Exception as e:
        print(f"⚠️  History comparison enrichment failed: {e}", file=sys.stderr)

    print("[5.8/9] Fetching governed macro/news announcements...")
    new_news_rows = []
    try:
        news_items = collect_news()
        news_dicts = [item.as_dict() for item in news_items]
        new_news_rows = insert_news_announcements(news_dicts)
        parsed["news_context"] = [item.as_dict() for item in news_items[:10]]
        parsed.setdefault("raw_series", {})["news_context"] = parsed["news_context"]
        print(f"    news candidates={len(news_items)} | new announcements={len(new_news_rows)}")
    except Exception as e:
        parsed["news_context"] = []
        print(f"⚠️  News collection failed (analysis continues without news): {e}", file=sys.stderr)

    # Deterministic state is prepared AFTER news so the same governed input
    # reaches both the analyst and the Telegram/LINE renderers.
    parsed = enrich_market_state(parsed, hist_context)
    market_state = (parsed.get("raw_series") or {}).get("market_state") or {}
    print(
        f"    market state: CFD={'OK' if market_state.get('cfd_complete') else 'UNKNOWN'} | "
        f"1H={'OK' if hist_context.get('hour_ago') else 'UNKNOWN'} | "
        f"Today={'OK' if hist_context.get('today', {}).get('count') else 'UNKNOWN'} | "
        f"Yesterday={'OK' if hist_context.get('yesterday', {}).get('count') else 'UNKNOWN'}"
    )

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

        future_price = parsed.get("future_price")
        cfd_price = parsed.get("cfd_price")

        def to_cfd(strike):
            if not isinstance(strike, (int, float)):
                return None
            if isinstance(future_price, (int, float)) and isinstance(cfd_price, (int, float)):
                return float(strike) - float(future_price) + float(cfd_price)
            # Never label a Futures strike as CFD when the basis is unavailable.
            return None

        strikes = sorted({
            float(row.get("strike"))
            for row in (gex.get("rows") or [])
            if isinstance(row, dict) and isinstance(row.get("strike"), (int, float))
        })

        def nearest_above(value, fallback=None):
            if not isinstance(value, (int, float)):
                return fallback
            candidates = [x for x in strikes if x > float(value)]
            return candidates[0] if candidates else fallback

        def nearest_below(value, fallback=None):
            if not isinstance(value, (int, float)):
                return fallback
            candidates = [x for x in strikes if x < float(value)]
            return candidates[-1] if candidates else fallback

        current_fut = future_price if isinstance(future_price, (int, float)) else None
        call_wall_fut = gex.get("call_wall")
        put_wall_fut = gex.get("put_wall")
        resistance_main_fut = call_wall_fut
        support_main_fut = put_wall_fut
        resistance_current_fut = nearest_above(current_fut, call_wall_fut)
        support_current_fut = nearest_below(current_fut, put_wall_fut)
        resistance_far_fut = nearest_above(call_wall_fut, resistance_current_fut)
        support_deep_fut = nearest_below(put_wall_fut, support_current_fut)

        resistance_current = to_cfd(resistance_current_fut)
        resistance_main = to_cfd(resistance_main_fut)
        resistance_far = to_cfd(resistance_far_fut)
        support_current = to_cfd(support_current_fut)
        support_main = to_cfd(support_main_fut)
        support_deep = to_cfd(support_deep_fut)

        fmt = lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "UNKNOWN"

        current_totals = (parsed.get("raw_series") or {}).get("totals") or {}
        news_available = bool(parsed.get("news_context"))

        ai_result = {
            "analysis_status": "DEGRADED",
            "market_overview": "รอบนี้ LLM output ไม่ผ่าน verification จึงใช้ deterministic market state เป็นฐาน โดยไม่ปั้นข้อสรุปใหม่",
            "what": (
                f"Futures {fmt(future_price)} | CFD {fmt(cfd_price)} | "
                f"Net GEX={fmt(gex.get('net_gex'))} | DTE={fmt(parsed.get('dte'))}"
            ),
            "why": "ยังมี source-derived OI/GEX/level สำหรับทำ conditional roadmap แต่ analyst narrative จาก LLM ใช้ไม่ได้ในรอบนี้",
            "positioning": (
                f"OI Put={fmt(current_totals.get('open_interest_put'))} | "
                f"Call={fmt(current_totals.get('open_interest_call'))} | "
                f"OI Change Put={fmt(current_totals.get('oi_change_put'))} | "
                f"Call={fmt(current_totals.get('oi_change_call'))} | "
                f"Churn={fmt(current_totals.get('churn'))}"
            ),
            "levels": {
                "resistance_far": resistance_far,
                "resistance_main": resistance_main,
                "resistance_current": resistance_current,
                "support_current": support_current,
                "support_main": support_main,
                "support_deep": support_deep,
            },
            "scenarios": {
                "bull": (
                    f"รอราคายืนเหนือ {fmt(resistance_current)} แล้ว Break/Hold เหนือ "
                    f"{fmt(resistance_main)}; Retest ต้องไม่เสียระดับ breakout"
                ),
                "bear": (
                    f"รอราคาหลุด {fmt(support_main)} แล้ว Retest ไม่ผ่าน; "
                    f"จึงติดตาม {fmt(support_current)} → {fmt(support_deep)}"
                ),
                "sideway": (
                    f"ถ้าราคายังอยู่ระหว่าง {fmt(support_main)} และ {fmt(resistance_main)} "
                    "โดยไม่มี trigger ชัดเจน ให้มองเป็น range"
                ),
            },
            "bias": "WAIT",
            "uncertainty": 1.0,
            "trade_plan": {
                "status": "CONDITIONAL",
                "direction": "WAIT",
                "entry": (
                    f"LONG: Break + Hold/Retest {fmt(resistance_current)} → {fmt(resistance_main)} | "
                    f"SHORT: Break + Retest Fail {fmt(support_main)}"
                ),
                "stop_loss": (
                    f"LONG invalidation: ต่ำกว่า {fmt(support_current)} | "
                    f"SHORT invalidation: เหนือ {fmt(resistance_current)}"
                ),
                "take_profit_1": (
                    f"LONG: {fmt(resistance_main)} | SHORT: {fmt(support_current)}"
                ),
                "take_profit_2": (
                    f"LONG: {fmt(resistance_far)} | SHORT: {fmt(support_deep)}"
                ),
                "setup": "Conditional plan จาก deterministic price levels; รอ price action/technical confirmation ก่อนเข้า",
                "trigger": "LONG = Break + Hold/Retest success; SHORT = Break + Retest failure",
                "confirmation": "ต้องมี price action/technical confirmation; ΔOI/OI baseline ที่ไม่มีให้ถือเป็น UNKNOWN",
                "invalidation": "เมื่อ breakout ไม่สามารถ hold/retest ได้ตามเงื่อนไข หรือราคากลับผ่าน invalidation",
                "risk_reward": "คำนวณจาก Entry/Stop/TP หลัง trigger ยืนยัน",
                "market_condition": "DEGRADED / PRICE-TRIGGER REQUIRED",
                "position_risk": "จำกัดความเสี่ยงต่อสถานะตามกติกาพอร์ตของผู้ใช้หลัง trigger ชัดเจน",
                "risk_note": "แผนนี้เป็น conditional roadmap ไม่ใช่คำสั่ง execute และไม่สร้างตัวเลขนอก deterministic evidence",
            },
            "data_limitations": [
                "LLM output rejected before delivery: " + str(ai_result.get("error")),
                "มี news evidence ใน input" if news_available else "ไม่มี news evidence ในรอบนี้",
                "DEGRADED fallback ไม่ตีความ Macro/News เพิ่มเกิน deterministic evidence",
            ],
            "market_regime": "TRANSITION_UNCERTAIN",
            "macro": "NEWS evidence available แต่ไม่ได้ให้ LLM narrative ในรอบนี้" if news_available else "UNKNOWN",
            "financial_engineering": (
                f"Net GEX={fmt(gex.get('net_gex'))} | "
                f"Call Wall={fmt(resistance_main)} | Put Wall={fmt(support_main)}"
            ),
            "market_microstructure": "ใช้เฉพาะ deterministic price/level mapping; ไม่มี order-flow claim เพิ่ม",
            "market_psychology": "UNKNOWN",
            "history_comparison": "ดู deterministic history fields ใน input; LLM narrative unavailable",
            "base_case": (
                f"ราคาแกว่งระหว่าง {fmt(support_main)} และ {fmt(resistance_main)} จนกว่าจะเกิด trigger"
            ),
            "alternative_case": (
                f"เหนือ {fmt(resistance_current)} มีโอกาสเปิด upside path; "
                f"ต่ำกว่า {fmt(support_main)} มีโอกาสเปิด downside path"
            ),
            "invalidation_case": "เมื่อ deterministic levels ไม่สอดคล้องกับ current snapshot",
            "final_trade_idea": (
                f"Conditional roadmap: LONG เหนือ {fmt(resistance_current)} ไป {fmt(resistance_main)} "
                f"หรือ SHORT ใต้ {fmt(support_main)} ไป {fmt(support_current)}"
            ),
            "evidence_refs": ["itb:oi:deterministic", "itb:oi:history"] + (["itb:news:latest"] if news_available else []),
        }
        print("    ⚠️ ใช้ DEGRADED V2: มี conditional trade roadmap จาก deterministic levels")

    # Hard post-processing boundary: the LLM may narrate, but it cannot
    # replace deterministic CFD levels, history coverage, or the requirement
    # to emit a conditional trade roadmap.
    ai_result = normalize_analyst_output(parsed, hist_context, ai_result)
    print(
        f"    analyst guardrails: status={ai_result.get('analysis_status')} "
        f"trade_plan={((ai_result.get('trade_plan') or {}).get('status') or 'UNKNOWN')} "
        f"direction={((ai_result.get('trade_plan') or {}).get('direction') or 'UNKNOWN')}"
    )

    print("[7/9] Inserting into Supabase...")
    import json
    
    row = insert_snapshot(
        parsed,
        ai_summary=json.dumps(ai_result, ensure_ascii=False),
        screenshot_path=screenshot_path,
        screenshot_url=screenshot_url,
        gamma_table_path=gamma_table_path,
        gamma_table_url=gamma_table_url,
        gamma_table_full_path=gamma_table_full_path,
        gamma_table_full_url=gamma_table_full_url,
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

    cooldown_minutes = max(0, int(os.environ.get("OI_BOT_NOTIFICATION_COOLDOWN_MINUTES", "30")))
    force_notify = os.environ.get("OI_BOT_FORCE_NOTIFY", "").strip().lower() in {"1", "true", "yes"}

    telegram_allowed = False
    try:
        telegram_allowed, remaining = can_notify("telegram", cooldown_minutes)
    except Exception as e:
        # Delivery state failure must not block analysis persistence. In an
        # unavailable state store, default to allowing one delivery.
        telegram_allowed = True
        remaining = None
        print(f"⚠️  Telegram cooldown state unavailable: {e}", file=sys.stderr)

    if force_notify or telegram_allowed:
        try:
            telegram.send(
                parsed,
                ai_result,
                screenshot_url=screenshot_url,
                gamma_table_url=gamma_table_url,
                gamma_table_full_url=gamma_table_full_url,
                chat_ids=chat_ids,
            )
            mark_notified("telegram")
            print("✅ Sent to Telegram")
        except Exception as e:
            print(f"⚠️  Telegram send failed (data still saved to Supabase): {e}", file=sys.stderr)
    else:
        print(
            f"⏭️  Telegram cooldown active — skip delivery for ~{remaining / 60:.1f} min. "
            "Set OI_BOT_FORCE_NOTIFY=1 to force a test delivery."
        )

    if new_news_rows:
        news_text = format_news_announcement(new_news_rows, limit=3)
        try:
            telegram.send_news(news_text, chat_ids=chat_ids)
            print("✅ Sent NEWS ANNOUNCEMENT to Telegram")
        except Exception as e:
            print(f"⚠️  Telegram news announcement failed: {e}", file=sys.stderr)

        if os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"):
            try:
                line.send_news(news_text)
                print("✅ Sent NEWS ANNOUNCEMENT to LINE")
            except Exception as e:
                print(f"⚠️  LINE news announcement failed: {e}", file=sys.stderr)

    print("[9/9] Sending to LINE (broadcast to all OA friends)...")
    if os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"):
        line_allowed = False
        try:
            line_allowed, line_remaining = can_notify("line", cooldown_minutes)
        except Exception as e:
            line_allowed = True
            line_remaining = None
            print(f"⚠️  LINE cooldown state unavailable: {e}", file=sys.stderr)

        if force_notify or line_allowed:
            try:
                line.send(
                    parsed,
                    ai_result,
                    screenshot_url=screenshot_url,
                    gamma_table_url=gamma_table_url,
                    gamma_table_full_url=gamma_table_full_url,
                )
                mark_notified("line")
                print("✅ Sent to LINE")
            except Exception as e:
                print(f"⚠️  LINE send failed (data still saved to Supabase): {e}", file=sys.stderr)
        else:
            print(
                f"⏭️  LINE cooldown active — skip delivery for ~{line_remaining / 60:.1f} min."
            )
    else:
        print("    ⏭️  ข้าม LINE (ไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN)")


if __name__ == "__main__":
    run()
