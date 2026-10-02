"""Telegram delivery for the verified human-readable OI analyst narrative.

Telegram is the proactive notification surface. It does not generate or invent
trade execution levels locally; deterministic market data and supaBOT output
remain the only sources of factual claims.
"""

from __future__ import annotations

import html
import os
import time
from datetime import datetime, timedelta, timezone

import requests


TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_API = "https://api.telegram.org/bot{token}/sendPhoto"
BANGKOK_TZ = timezone(timedelta(hours=7))
MAX_MESSAGE_LEN = 3900


def _thai_datetime_str(dt: datetime | None = None) -> str:
    months = [
        "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
        "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
    ]
    dt = (dt or datetime.now(timezone.utc)).astimezone(BANGKOK_TZ)
    return f"วันที่ {dt.day} {months[dt.month]} {dt.year + 543} | เวลา {dt:%H:%M} น."


def _compact(value: object, limit: int = 500) -> str:
    text = " ".join(str(value or "-").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def _escape(value: object) -> str:
    return html.escape(str(value or "-"), quote=False)


def _chunk(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks


def _format_source_message(parsed: dict) -> str:
    raw = parsed.get("raw_series") or {}
    window = raw.get("gold_series_window") or []
    gamma = raw.get("multi_expiry_gamma") or {}
    observed = sum(1 for c in (gamma.get("columns") or []) if c.get("status") == "OBSERVED")

    lines = [
        "<b>GOLD OPTIONS • 7-DAY TERM STRUCTURE</b>",
        "Source: CME QuikStrike",
        f"Observed: <b>{observed}/7</b> series",
        "",
    ]
    for item in window[:7]:
        code = item.get("code") or "UNKNOWN"
        date = str(item.get("expiry_date") or "")
        date_label = f"{date[8:10]}/{date[5:7]}" if len(date) >= 10 else "--/--"
        status = "✓" if item.get("status") == "OBSERVED" else "—"
        dte = item.get("dte")
        dte_label = f"DTE {dte:.2f}" if isinstance(dte, (int, float)) else "DTE —"
        lines.append(f"{status} {date_label} {item.get('weekday_short','')} · <b>{_escape(code)}</b> · {dte_label}")

    lines += [
        "",
        "ราคาบนลงล่างใน Gamma Table • ช่องว่าง = ยังไม่มี source observation",
    ]
    return "\n".join(lines)


def _format_analysis_message(parsed: dict, ai_result: dict) -> str:
    """Render the complete V2 analyst narrative as message 3."""
    dte = parsed.get("dte")
    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}

    def show(value):
        return "-" if value is None or value == "" else str(value)

    header = (
        f"<b>GOLD MARKET ANALYST V2 • {_thai_datetime_str()}</b>\n"
        f"Futures {show(parsed.get('future_price'))} | CFD {show(parsed.get('cfd_price'))} | DTE {show(dte)}\n"
        f"Status: <b>{_escape(str(ai_result.get('analysis_status') or 'CONFIRMED').upper())}</b> | "
        f"Bias: <b>{_escape(str(ai_result.get('bias') or 'WAIT').upper())}</b>"
    )

    parts = [
        header,
        "",
        "<b>WHAT</b>",
        _escape(ai_result.get("what") or ai_result.get("market_overview") or "-"),
        "",
        "<b>WHY</b>",
        _escape(ai_result.get("why") or "-"),
        "",
        "<b>POSITIONING</b>",
        _escape(ai_result.get("positioning") or "-"),
    ]

    return "\n".join(parts)


def _format_levels_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    levels = ai_result.get("levels") or {}

    def show(value):
        return "-" if value is None or value == "" else str(value)

    columns = gamma.get("columns") or []
    expiration_count = len(columns)
    positive = zones.get("highest_positive_gamma")
    negative = zones.get("highest_negative_gamma")

    return (
        "<b>KEY LEVELS</b>\n"
        f"ต้านไกล: {show(levels.get('resistance_far'))}\n"
        f"ต้านหลัก: {show(levels.get('resistance_main'))}\n"
        f"ต้านใกล้: {show(levels.get('resistance_current'))}\n"
        f"รับใกล้: {show(levels.get('support_current'))}\n"
        f"รับหลัก: {show(levels.get('support_main'))}\n"
        f"รับลึก: {show(levels.get('support_deep'))}\n\n"
        "<b>GAMMA TERM STRUCTURE</b>\n"
        f"{expiration_count} expirations | +GEX zone {show(positive)} | -GEX zone {show(negative)}\n\n"
        "<b>SCENARIOS</b>\n"
        f"🟢 <b>Bull</b> — {_escape((ai_result.get('scenarios') or {}).get('bull') or '-')}\n"
        f"🔴 <b>Bear</b> — {_escape((ai_result.get('scenarios') or {}).get('bear') or '-')}\n"
        f"🟡 <b>Sideway</b> — {_escape((ai_result.get('scenarios') or {}).get('sideway') or '-')}"
    )


def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    trade = ai_result.get("trade_plan") or {}
    return (
        "<b>TRADE PLAN</b>\n"
        f"Status: {_escape(str(trade.get('status') or 'NO_TRADE').upper())}\n"
        f"{_escape(trade.get('setup') or '-')}\n"
        f"Confirmation: {_escape(trade.get('confirmation') or '-')}\n"
        f"Invalidation: {_escape(trade.get('invalidation') or '-')}\n"
        f"Risk: {_escape(trade.get('risk_note') or '-')}"
    )


def format_message(parsed: dict, ai_result: dict) -> str:
    """Backward-compatible alias for the second message."""
    return _format_analysis_message(parsed, ai_result)


def _post_with_retry(url: str, payload: dict, timeout: int = 20) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            if response.status_code < 400:
                return
            if response.status_code == 429:
                retry_after = 2
                try:
                    retry_after = int((response.json().get("parameters") or {}).get("retry_after", 2))
                except Exception:
                    pass
                time.sleep(max(1, min(retry_after, 10)))
                continue
            if response.status_code >= 500:
                time.sleep(1.0 * (attempt + 1))
                continue
            response.raise_for_status()
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("TELEGRAM_SEND_FAILED")


def send(
    parsed: dict,
    ai_result: dict,
    screenshot_url: str | None = None,
    chat_ids: list[str] | None = None,
    gamma_table_url: str | None = None,
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ไม่ได้ตั้งค่า")
    if chat_ids is None:
        raise RuntimeError("ต้องระบุ chat_ids ที่ผ่านการอนุมัติจาก customer registry")
    chat_ids = [str(cid).strip() for cid in chat_ids if str(cid).strip()]
    if not chat_ids:
        raise RuntimeError("ไม่มี authorized chat_ids ให้ส่ง")

    messages = [
        _format_analysis_message(parsed, ai_result),
        _format_levels_message(parsed, ai_result),
        _format_trade_plan_message(parsed, ai_result),
    ]
    bias_message = f"🎯 Bias ฟันธง!\n{str(ai_result.get('bias', ai_result.get('short_bias', 'WAIT')))}"

    for cid in chat_ids:
        if gamma_table_url:
            _post_with_retry(
                TELEGRAM_PHOTO_API.format(token=token),
                {"chat_id": cid, "photo": gamma_table_url, "caption": "GOLD GAMMA TABLE — Multi-Expiration"},
            )
        if screenshot_url:
            _post_with_retry(
                TELEGRAM_PHOTO_API.format(token=token),
                {"chat_id": cid, "photo": screenshot_url, "caption": "QUIKSTRIKE OI — Source Screenshot"},
            )
        for text in (*messages, bias_message):
            # The fifth message should be the trade plan. Keep Bias out of the
            # canonical five-message bundle unless it is needed for legacy callers.
            pass
        # Exact 5-message delivery: 2 images + analyst + levels/scenarios + trade plan.
        for text in messages:
            for chunk in _chunk(text):
                _post_with_retry(
                    TELEGRAM_API.format(token=token),
                    {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
                )
                time.sleep(0.4)
        print(f"✅ Telegram 5-message analyst bundle sent to {cid}")
