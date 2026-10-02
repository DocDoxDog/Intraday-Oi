"""LINE delivery for the GOLD Market Analyst."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests


LINE_BROADCAST_API = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"
MAX_MESSAGES_PER_REQUEST = 5


def _text_message(text: str) -> dict:
    return {"type": "text", "text": text[:5000]}


def _image_message(url: str) -> dict:
    return {
        "type": "image",
        "originalContentUrl": url,
        "previewImageUrl": url,
    }


def _show(value, digits=2) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, (int, float)):
        return f"{float(value):,.{digits}f}"
    text = str(value).strip()
    try:
        return f"{float(text):,.{digits}f}"
    except ValueError:
        return text


def format_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    news = parsed.get("news_context") or []

    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7)))
    months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    date_text = f"วันที่ {now.day} {months[now.month]} {now.year + 543} | เวลา {now:%H:%M} น."

    lines = [
        f"GOLD MARKET ANALYST V2 • {date_text}",
        f"Futures {_show(parsed.get('future_price'))} | CFD {_show(parsed.get('cfd_price'))} | "
        f"Basis {_show(parsed.get('basis_diff'))} (FUTURES - CFD) | DTE {_show(parsed.get('dte'))}",
        f"Status: {str(ai_result.get('analysis_status') or 'CONFIRMED').upper()} | "
        f"Bias: {str(ai_result.get('bias') or 'WAIT').upper()}",
        "",
        "MARKET STATE",
        f"Regime: {ai_result.get('market_regime') or '-'}",
        ai_result.get("what") or ai_result.get("market_overview") or "-",
        "",
        "DRIVERS",
        f"Macro: {ai_result.get('macro') or '-'}",
        f"Financial Engineering: {ai_result.get('financial_engineering') or '-'}",
        f"Microstructure: {ai_result.get('market_microstructure') or '-'}",
        f"Psychology: {ai_result.get('market_psychology') or '-'}",
        "",
        "WHY / POSITIONING",
        ai_result.get("why") or "-",
        ai_result.get("positioning") or "-",
        "",
        "FLOW & HISTORY",
        f"OI Put {_show(totals.get('open_interest_view_put', totals.get('open_interest_put')))} | "
        f"Call {_show(totals.get('open_interest_view_call', totals.get('open_interest_call')))} | "
        f"Total {_show(totals.get('open_interest_view_total', totals.get('open_interest_total')))}",
        f"OI Change Put {_show(totals.get('oi_change_put'))} | "
        f"Call {_show(totals.get('oi_change_call'))} | "
        f"Total {_show(totals.get('oi_change_total'))}",
        f"ΔOI vs baseline Put {_show(totals.get('oi_delta_put'))} | "
        f"Call {_show(totals.get('oi_delta_call'))} | "
        f"Total {_show(totals.get('oi_delta_total'))}",
        f"Churn Put {_show(totals.get('quikstrike_churn_put'))} | "
        f"Call {_show(totals.get('quikstrike_churn_call'))} | "
        f"Total {_show(totals.get('churn'))}",
        f"Volume Put {_show(parsed.get('put_volume'))} | Call {_show(parsed.get('call_volume'))}",
        f"IV {_show(parsed.get('vol'))}% | IV Δ {_show(parsed.get('vol_chg'))}%",
        ai_result.get("history_comparison") or "-",
    ]
    if news:
        lines += ["", "NEWS CONTEXT"]
        for item in news[:2]:
            lines.append(
                f"• {item.get('headline') or '-'}\n"
                f"  {item.get('source') or '-'} | {item.get('published_at') or '-'}"
            )
    return "\n".join(lines)


def _levels_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    levels = ai_result.get("levels") or {}
    scenarios = ai_result.get("scenarios") or {}
    show = lambda v: _show(v)
    return "\n".join([
        "KEY LEVELS (CFD)",
        f"🔴 ต้านไกล: {show(levels.get('resistance_far'))}",
        f"🔴 ต้านหลัก: {show(levels.get('resistance_main'))}",
        f"🟠 ต้านใกล้: {show(levels.get('resistance_current'))}",
        f"🟢 รับใกล้: {show(levels.get('support_current'))}",
        f"🟢 รับหลัก: {show(levels.get('support_main'))}",
        f"🟢 รับลึก: {show(levels.get('support_deep'))}",
        "",
        "GAMMA TERM STRUCTURE",
        f"{len(gamma.get('columns') or [])} expirations | "
        f"+GEX zone {show(zones.get('highest_positive_gamma'))} | "
        f"-GEX zone {show(zones.get('highest_negative_gamma'))}",
        "",
        "SCENARIOS",
        f"🟢 Bull — {scenarios.get('bull') or '-'}",
        f"🔴 Bear — {scenarios.get('bear') or '-'}",
        f"🟡 Sideway — {scenarios.get('sideway') or '-'}",
        "",
        "CASE MAP",
        f"BASE — {ai_result.get('base_case') or '-'}",
        f"ALT — {ai_result.get('alternative_case') or '-'}",
        f"INVALIDATION — {ai_result.get('invalidation_case') or '-'}",
    ])


def _trade_plan_message(parsed: dict, ai_result: dict) -> str:
    trade = ai_result.get("trade_plan") or {}
    return "\n".join([
        "TRADE PLAN",
        f"Status: {str(trade.get('status') or 'CONDITIONAL').upper()}",
        f"Direction: {trade.get('direction') or 'WAIT'}",
        f"Entry: {trade.get('entry') or 'UNKNOWN'}",
        f"Stop: {trade.get('stop_loss') or 'UNKNOWN'}",
        f"TP1: {trade.get('take_profit_1') or 'UNKNOWN'}",
        f"TP2: {trade.get('take_profit_2') or 'UNKNOWN'}",
        "",
        f"Trigger: {trade.get('trigger') or 'UNKNOWN'}",
        f"Invalidation: {trade.get('invalidation') or 'UNKNOWN'}",
        f"Risk/Reward: {trade.get('risk_reward') or 'UNKNOWN'}",
        f"Market Condition: {trade.get('market_condition') or 'UNKNOWN'}",
        f"Position Risk: {trade.get('position_risk') or 'UNKNOWN'}",
        f"Risk: {trade.get('risk_note') or 'UNKNOWN'}",
        "",
        "FINAL TRADE IDEA",
        ai_result.get("final_trade_idea") or trade.get("setup") or "UNKNOWN",
    ])


def _post_broadcast(token: str, messages: list[dict]) -> None:
    response = requests.post(
        LINE_BROADCAST_API,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messages": messages},
        timeout=20,
    )
    if response.status_code != 200:
        raise RuntimeError(f"LINE broadcast ล้มเหลว [{response.status_code}]: {response.text}")


def _post_push(token: str, to: str, messages: list[dict]) -> None:
    response = requests.post(
        LINE_PUSH_API,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"to": to, "messages": messages},
        timeout=20,
    )
    if response.status_code != 200:
        raise RuntimeError(f"LINE group push ล้มเหลว [{response.status_code}]: {response.text}")


def send_news(news_text: str) -> None:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN ไม่ได้ตั้งค่า")
    plain = re.sub(r"<[^>]+>", "", news_text)
    _post_broadcast(token, [_text_message(plain)])
    print("✅ ส่ง LINE NEWS ANNOUNCEMENT สำเร็จ")


def send(
    parsed: dict,
    ai_result: dict,
    screenshot_url: str | None = None,
    gamma_table_url: str | None = None,
    gamma_table_full_url: str | None = None,
) -> None:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN ไม่ได้ตั้งค่า")

    messages: list[dict] = []
    if gamma_table_url:
        messages.append(_image_message(gamma_table_url))
    if gamma_table_full_url:
        messages.append(_image_message(gamma_table_full_url))
    if screenshot_url:
        messages.append(_image_message(screenshot_url))
    messages.extend([
        _text_message(format_message(parsed, ai_result)),
        _text_message(_levels_message(parsed, ai_result)),
        _text_message(_trade_plan_message(parsed, ai_result)),
    ])

    errors: list[str] = []
    for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
        chunk = messages[i:i + MAX_MESSAGES_PER_REQUEST]
        try:
            _post_broadcast(token, chunk)
            print(f"✅ ส่ง LINE broadcast สำเร็จ ({len(chunk)} ข้อความ)")
        except Exception as exc:
            print(f"❌ ส่ง LINE broadcast ล้มเหลว: {exc}")
            errors.append(str(exc))
        time.sleep(0.5)

    group_id = os.environ.get("LINE_GROUP_ID", "").strip()
    if group_id:
        for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
            chunk = messages[i:i + MAX_MESSAGES_PER_REQUEST]
            try:
                _post_push(token, group_id, chunk)
                print(f"✅ ส่ง LINE group push สำเร็จ ({len(chunk)} ข้อความ)")
            except Exception as exc:
                print(f"❌ ส่ง LINE group push ล้มเหลว: {exc}")
                errors.append(str(exc))
            time.sleep(0.5)
    else:
        print("⏭️ ข้าม LINE group push (ไม่ได้ตั้งค่า LINE_GROUP_ID)")

    if errors:
        raise RuntimeError(
            f"LINE broadcast ล้มเหลว {len(errors)} chunk(s): " + " | ".join(errors)
        )
