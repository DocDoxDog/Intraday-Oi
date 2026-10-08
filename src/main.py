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
    persist_market_bars,
    insert_oi_intelligence,
    insert_multi_expiry_options,
    upload_screenshot,
    get_active_chat_ids,
    insert_news_announcements,
    can_notify,
    mark_notified,
)
from src.url_manager import UrlManager, UrlManagerError
from src import history, telegram, line
from src.multi_expiry import build_gamma_matrix, summarize_gamma_zones, merge_expected_expirations, build_gold_weekly_series_window
from src.gamma_chart import render_gamma_table, render_gamma_table_full
from src.news_announcement import collect_news, format_news_announcement
from src.market_state import enrich_market_state, normalize_analyst_output
from src.macro_state import build_macro_state
from src.quant_metrics import enrich_quant_metrics
from src.market_flow_engine import build_flow_context
from intelligence.news.free_feed import collect_free_news


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
            market_bars = parsed["technical_context"].pop("_market_bars", {})
            try:
                persisted_bars = persist_market_bars(
                    market_bars,
                    instrument=parsed["technical_context"].get("symbol") or "XAU/USD",
                )
                print(f"    OHLC persisted to market_bars: {persisted_bars} bars")
            except Exception as persist_error:
                # OHLC persistence failure must not fabricate technical evidence.
                print(f"⚠️  OHLC persistence failed; current technical analysis remains in-memory only: {persist_error}", file=sys.stderr)
            confirmation = parsed["technical_context"].get("confirmation", {})
            print(
                f"    bias={confirmation.get('bias')} "
                f"htf_aligned={confirmation.get('htf_aligned')}"
            )
        except Exception as e:
            print(f"⚠️  Technical confirmation failed (AI will use Options data only): {e}", file=sys.stderr)
    else:
        print("    ⏭️  ข้าม technical confirmation (ไม่มี Twelve Data key)")

    print("[4/9] Preparing Gamma Table + OI screenshot assets...")
    # Gamma rendering waits until history is available so the image header can
    # show the same timestamp/market context and a deterministic 1H GEX change.
    screenshot_bytes = parsed.pop("screenshot", None)
    screenshot_path = None
    screenshot_url = None
    gamma_table_path = None
    gamma_table_url = None
    gamma_table_full_path = None
    gamma_table_full_url = None
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
    print(
        f"    QuikStrike OI CHANGE put={oi_totals.get('oi_change_put') if oi_totals.get('oi_change_put') is not None else 'UNKNOWN'} "
        f"call={oi_totals.get('oi_change_call') if oi_totals.get('oi_change_call') is not None else 'UNKNOWN'} "
        f"total={oi_totals.get('oi_change_total') if oi_totals.get('oi_change_total') is not None else 'UNKNOWN'} | "
        f"CHURN put={oi_totals.get('quikstrike_churn_put') if oi_totals.get('quikstrike_churn_put') is not None else 'UNKNOWN'} "
        f"call={oi_totals.get('quikstrike_churn_call') if oi_totals.get('quikstrike_churn_call') is not None else 'UNKNOWN'} "
        f"total={oi_totals.get('churn') if oi_totals.get('churn') is not None else 'UNKNOWN'}"
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

    print("[5.7/9] Rendering + uploading Gamma Table with snapshot context...")
    gamma_matrix = (parsed.get("raw_series") or {}).get("multi_expiry_gamma")
    if gamma_matrix and gamma_matrix.get("status") == "VALID":
        try:
            raw_series = parsed.get("raw_series") or {}
            gex = raw_series.get("gex") or {}
            current_gex = gex.get("net_gex")
            hour_raw = (hist_context.get("hour_ago") or {}).get("raw_series") or {}
            hour_gex = (hour_raw.get("gex") or {}).get("net_gex")
            try:
                current_gex = float(current_gex) if current_gex is not None else None
            except (TypeError, ValueError):
                current_gex = None
            try:
                hour_gex = float(hour_gex) if hour_gex is not None else None
            except (TypeError, ValueError):
                hour_gex = None

            display_context = {
                "observed_at": parsed.get("observed_at") or parsed.get("retrieved_at"),
                "future_price": parsed.get("future_price"),
                "cfd_price": parsed.get("cfd_price"),
                "basis_diff": parsed.get("basis_diff"),
                "iv": parsed.get("vol"),
                "gex_change_1h": (
                    current_gex - hour_gex
                    if current_gex is not None and hour_gex is not None
                    else None
                ),
            }
            gamma_matrix["display_context"] = display_context

            gamma_bytes = render_gamma_table(gamma_matrix, context=display_context)
            uploaded_gamma = upload_screenshot(
                gamma_bytes, contract=f"{parsed.get('contract')}_GAMMA_COMPACT"
            )
            if uploaded_gamma:
                gamma_table_path = uploaded_gamma["path"]
                gamma_table_url = uploaded_gamma["signed_url"]

            full_bytes = render_gamma_table_full(gamma_matrix, context=display_context)
            uploaded_full = upload_screenshot(
                full_bytes, contract=f"{parsed.get('contract')}_GAMMA_FULL"
            )
            if uploaded_full:
                gamma_table_full_path = uploaded_full["path"]
                gamma_table_full_url = uploaded_full["signed_url"]
            print("    ✅ Gamma Table compact(30 rows) + full uploaded")
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

    print("[5.8/9] Fetching governed macro/news announcements...")
    new_news_rows = []
    try:
        governed_items = collect_news()
        free_items, _free_clusters = collect_free_news()

        # Keep the legacy governed feeds, but add free macro-calendar and
        # geopolitical discovery. De-duplicate exact source/url/headline/time
        # collisions and keep the most recently observed item.
        combined = [item.as_dict() for item in governed_items]
        combined.extend(item.as_legacy_dict() for item in free_items)
        deduped = {}
        for item in combined:
            key = (
                str(item.get("source") or "").strip().lower(),
                str(item.get("url") or "").strip(),
                str(item.get("headline") or "").strip().lower(),
                str(item.get("published_at") or "").strip(),
            )
            deduped[key] = item
        news_dicts = sorted(
            deduped.values(),
            key=lambda item: str(item.get("published_at") or ""),
            reverse=True,
        )[:30]

        new_news_rows = insert_news_announcements(news_dicts)
        parsed["news_context"] = news_dicts[:12]
        parsed.setdefault("raw_series", {})["news_context"] = parsed["news_context"]
        print(
            f"    news candidates={len(news_dicts)} "
            f"(governed={len(governed_items)} free={len(free_items)}) "
            f"| new announcements={len(new_news_rows)}"
        )
    except Exception as e:
        parsed["news_context"] = []
        print(f"⚠️  News collection failed (analysis continues without news): {e}", file=sys.stderr)

    # Slow macro context is optional and fail-open. It is never allowed to
    # block QuikStrike analysis or become an entry trigger.
    if os.environ.get("ENABLE_FRED_MACRO", "1").strip().lower() not in {"0", "false", "no", "off"}:
        try:
            parsed.setdefault("raw_series", {})["macro_state"] = build_macro_state(
                api_key=os.environ.get("FRED_API_KEY")
            )
            print(
                f"    macro: status={parsed['raw_series']['macro_state'].get('status')} "
                f"bias={parsed['raw_series']['macro_state'].get('macro_bias')} "
                f"as_of={parsed['raw_series']['macro_state'].get('as_of')}"
            )
        except Exception as e:
            parsed.setdefault("raw_series", {})["macro_state"] = {
                "version": "macro-state-v1",
                "source": "fred",
                "status": "UNKNOWN",
                "macro_bias": "UNKNOWN",
                "error": type(e).__name__,
            }
            print(f"⚠️  Macro state failed (continuing without macro): {e}", file=sys.stderr)
    else:
        parsed.setdefault("raw_series", {})["macro_state"] = {
            "version": "macro-state-v1", "source": "fred",
            "status": "UNKNOWN", "macro_bias": "UNKNOWN",
            "limitations": ["Disabled by ENABLE_FRED_MACRO."],
        }

    # Deterministic state is prepared AFTER news so the same governed input
    # reaches both the analyst and the Telegram/LINE renderers.
    parsed = enrich_market_state(parsed, hist_context)
    parsed = enrich_quant_metrics(parsed, hist_context)
    # Deterministic flow layer: real OHLC + observed option nodes -> conditional path.
    try:
        flow_context = build_flow_context(parsed)
        parsed.setdefault("raw_series", {})["market_flow"] = flow_context
        parsed["raw_series"]["market_state"]["path"] = flow_context.get("path") or {}
        parsed["raw_series"]["market_state"]["price_memory"] = flow_context.get("price_memory") or {}
        print(
            "    market flow: status={} nodes={}".format(
                flow_context.get("status"), len(flow_context.get("nodes") or [])
            )
        )
    except Exception as e:
        parsed.setdefault("raw_series", {})["market_flow"] = {
            "status": "UNKNOWN", "error": type(e).__name__
        }
        print(f"⚠️  Market flow engine failed (analysis continues): {e}", file=sys.stderr)
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
        # LLM failure must degrade analyst quality, not collapse the market read into a raw data dump.
        from src.deterministic_analyst import build_deterministic_fallback
        ai_result = build_deterministic_fallback(
            parsed, hist_context, error=str(ai_result.get("error") or "LLM_UNAVAILABLE")
        )
        print("    ⚠️ ใช้ deterministic analyst fallback: conditional roadmap preserved")

    # Hard post-processing boundary: the LLM may narrate, but it cannot
    # replace deterministic CFD levels, history coverage, or the requirement
    # to emit a conditional trade roadmap.
    ai_result = normalize_analyst_output(parsed, hist_context, ai_result)
    # Deterministic path is authoritative; LLM cannot replace observed nodes.
    flow_context = (parsed.get("raw_series") or {}).get("market_flow") or {}
    if flow_context.get("status") == "VALID":
        ai_result["market_flow"] = {
            "version": flow_context.get("version"),
            "read": flow_context.get("market_read"),
            "flow": flow_context.get("flow_read"),
        }
        ai_result["structural_path"] = flow_context.get("path") or {}
        ai_result["price_memory"] = flow_context.get("price_memory") or {}
        ai_result["structural_nodes"] = flow_context.get("nodes") or []
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
