"""LINE delivery for the GOLD Market Analyst."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from src.customer_narrative import build_customer_narrative, _friendly_bias, _friendly_regime


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


def _thai_datetime_str(dt: datetime | None = None) -> str:
    months = [
        "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
        "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
    ]
    dt = (dt or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=7)))
    return f"วันที่ {dt.day} {months[dt.month]} {dt.year + 543} | เวลา {dt:%H:%M} น."

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
    """Render the same analysis-first narrative used by Telegram."""
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    narrative = build_customer_narrative(parsed, ai_result)
    status = str(ai_result.get("analysis_status") or "CONFIRMED").upper()
    bias = str(ai_result.get("bias") or "WAIT").upper()

    return "\n".join([
        f"GOLD MARKET ANALYST • {_thai_datetime_str()}",
        f"Futures {_show(parsed.get('future_price'))} | CFD {_show(parsed.get('cfd_price'))} | "
        f"Basis {_show(parsed.get('basis_diff'))} | DTE {_show(parsed.get('dte'))}",
        f"สถานะ: {status} | มุมมอง: {narrative_bias(bias)}",
        f"Regime: {narrative_regime(ai_result.get('market_regime') or (state.get('regime') or {}).get('regime'))}",
        "",
        "MARKET READ",
        narrative["market_read"],
        "",
        "VOLATILITY — ตลาดกำลังผันผวนแค่ไหน",
        narrative["volatility"],
        "",
        "OI POSITIONING — ผู้เล่นกำลังเพิ่ม/ลดสถานะอย่างไร",
        narrative["oi_positioning"],
        "",
        "FLOW STATEMENT — ภาพรวมแรงที่กำลังเกิดขึ้น",
        narrative["flow_statement"],
        "",
        "WHY NOW — ทำไมต้องจับตาตอนนี้",
        narrative["why_now"],
        "",
        "TECHNICAL",
        narrative["technical"],
        "",
        "MACROECONOMIC / NEWS",
        narrative["macro_news"],
        "",
        "หมายเหตุ: ตัวเลข OI / IV / Gamma เป็นหลักฐานประกอบการวิเคราะห์ ไม่ใช่สัญญาณซื้อขายโดยตรง",
    ])


def narrative_regime(value: object) -> str:
    return _friendly_regime(value)


def narrative_bias(value: object) -> str:
    return _friendly_bias(value)


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


def _is_monthly_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "monthly limit" in text or "monthly_limit" in text


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
    quota_exhausted = False
    for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
        chunk = messages[i:i + MAX_MESSAGES_PER_REQUEST]
        try:
            _post_broadcast(token, chunk)
            print(f"✅ ส่ง LINE broadcast สำเร็จ ({len(chunk)} ข้อความ)")
        except Exception as exc:
            if _is_monthly_limit_error(exc):
                print("⏭️ ข้าม LINE ที่เหลือ: LINE OA monthly message limit reached")
                quota_exhausted = True
                break
            print(f"❌ ส่ง LINE broadcast ล้มเหลว: {exc}")
            errors.append(str(exc))
        time.sleep(0.5)

    group_id = os.environ.get("LINE_GROUP_ID", "").strip()
    if group_id and not quota_exhausted:
        for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
            chunk = messages[i:i + MAX_MESSAGES_PER_REQUEST]
            try:
                _post_push(token, group_id, chunk)
                print(f"✅ ส่ง LINE group push สำเร็จ ({len(chunk)} ข้อความ)")
            except Exception as exc:
                if _is_monthly_limit_error(exc):
                    print("⏭️ ข้าม LINE group push: LINE OA monthly message limit reached")
                    quota_exhausted = True
                    break
                print(f"❌ ส่ง LINE group push ล้มเหลว: {exc}")
                errors.append(str(exc))
            time.sleep(0.5)
    else:
        print("⏭️ ข้าม LINE group push (ไม่ได้ตั้งค่า LINE_GROUP_ID)")

    if errors:
        raise RuntimeError(
            f"LINE broadcast ล้มเหลว {len(errors)} chunk(s): " + " | ".join(errors)
        )
