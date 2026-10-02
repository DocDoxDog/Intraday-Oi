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
    """Readable analyst message with strong section hierarchy."""
    def show(value, digits=2):
        if value is None or value == "":
            return "-"
        if isinstance(value, (int, float)):
            return f"{float(value):.{digits}f}"
        return str(value)

    sections = [
        f"<b>GOLD MARKET ANALYST V2</b>\n{_thai_datetime_str()}",
        f"<b>Futures</b> {show(parsed.get('future_price'))}  |  <b>CFD</b> {show(parsed.get('cfd_price'))}  |  <b>DTE</b> {show(parsed.get('dte'))}",
        f"<b>Status</b> {_escape(str(ai_result.get('analysis_status') or 'CONFIRMED').upper())}  |  <b>Bias</b> {_escape(str(ai_result.get('bias') or 'WAIT').upper())}",
        "",
        "<b>FLOW SNAPSHOT</b>",
        f"OI  Put {_escape(show(totals.get('open_interest_view_put', totals.get('open_interest_put'))))}  |  Call {_escape(show(totals.get('open_interest_view_call', totals.get('open_interest_call'))))}",
        f"ΔOI Put {_escape(show(totals.get('oi_delta_put', totals.get('oi_change_put'))))}  |  Call {_escape(show(totals.get('oi_delta_call', totals.get('oi_change_call')))}",
        f"Churn {_escape(show(totals.get('churn')))}  |  IV {_escape(show(parsed.get('vol')))}%",
        "",
        "<b>MARKET REGIME</b>",
        _escape(ai_result.get("market_regime") or "UNKNOWN"),
        "",
        "<b>MACRO</b>",
        _escape(ai_result.get("macro") or "UNKNOWN"),
        "",
        "<b>FINANCIAL ENGINEERING</b>",
        _escape(ai_result.get("financial_engineering") or "-"),
        "",
        "<b>MARKET MICROSTRUCTURE</b>",
        _escape(ai_result.get("market_microstructure") or "-"),
        "",
        "<b>MARKET PSYCHOLOGY</b>",
        _escape(ai_result.get("market_psychology") or "-"),
        "",
        "<b>WHAT</b>",
        _escape(ai_result.get("what") or ai_result.get("market_overview") or "-"),
        "",
        "<b>WHY</b>",
        _escape(ai_result.get("why") or "-"),
        "",
        "<b>POSITIONING</b>",
        _escape(ai_result.get("positioning") or "-"),
        "",
        "<b>HISTORY CHANGE</b>",
        _escape(ai_result.get("history_comparison") or "-"),
    ]
    return "\n".join(sections)


def _format_levels_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    levels = ai_result.get("levels") or {}
    scenarios = ai_result.get("scenarios") or {}

    def show(value):
        if value is None or value == "":
            return "-"
        if isinstance(value, (int, float)):
            return f"{float(value):.2f}"
        return str(value)

    return (
        "<b>KEY LEVELS</b>\n"
        f"🔴 ต้านไกล: <b>{show(levels.get('resistance_far'))}</b>\n"
        f"🔴 ต้านหลัก: <b>{show(levels.get('resistance_main'))}</b>\n"
        f"🟠 ต้านใกล้: <b>{show(levels.get('resistance_current'))}</b>\n"
        f"🟢 รับใกล้: <b>{show(levels.get('support_current'))}</b>\n"
        f"🟢 รับหลัก: <b>{show(levels.get('support_main'))}</b>\n"
        f"🟢 รับลึก: <b>{show(levels.get('support_deep'))}</b>\n\n"
        "<b>GAMMA TERM STRUCTURE</b>\n"
        f"<b>{len(gamma.get('columns') or [])}</b> expirations | "
        f"+GEX zone <b>{show(zones.get('highest_positive_gamma'))}</b> | "
        f"-GEX zone <b>{show(zones.get('highest_negative_gamma'))}</b>\n\n"
        "<b>SCENARIOS</b>\n"
        f"🟢 <b>Bull</b> — {_escape(scenarios.get('bull') or '-')}\n"
        f"🔴 <b>Bear</b> — {_escape(scenarios.get('bear') or '-')}\n"
        f"🟡 <b>Sideway</b> — {_escape(scenarios.get('sideway') or '-')}\n\n"
        "<b>CASE MAP</b>\n"
        f"BASE: {_escape(ai_result.get('base_case') or '-')}\n"
        f"ALT: {_escape(ai_result.get('alternative_case') or '-')}\n"
        f"INVALIDATION: {_escape(ai_result.get('invalidation_case') or '-')}"
    )


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
        f"Status: {_escape(str(trade.get('status') or 'CONDITIONAL').upper())}\n"
        f"Direction: {_escape(trade.get('direction') or 'WAIT')}\n"
        f"Entry: {_escape(trade.get('entry') or 'UNKNOWN')}\n"
        f"Stop: {_escape(trade.get('stop_loss') or 'UNKNOWN')}\n"
        f"TP1: {_escape(trade.get('take_profit_1') or 'UNKNOWN')}\n"
        f"TP2: {_escape(trade.get('take_profit_2') or 'UNKNOWN')}\n"
        f"Trigger: {_escape(trade.get('trigger') or 'UNKNOWN')}\n"
        f"Invalidation: {_escape(trade.get('invalidation') or 'UNKNOWN')}\n"
        f"Risk/Reward: {_escape(trade.get('risk_reward') or 'UNKNOWN')}\n"
        f"Market Condition: {_escape(trade.get('market_condition') or 'UNKNOWN')}\n"
        f"Position Risk: {_escape(trade.get('position_risk') or 'UNKNOWN')}\n"
        f"Risk: {_escape(trade.get('risk_note') or 'UNKNOWN')}"
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


def send_news(news_text: str, *, chat_ids: list[str]) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ไม่ได้ตั้งค่า")
    if not chat_ids:
        return
    for cid in [str(x).strip() for x in chat_ids if str(x).strip()]:
        for chunk in _chunk(news_text):
            _post_with_retry(
                TELEGRAM_API.format(token=token),
                {"chat_id": cid, "text": chunk},
            )
        print(f"✅ Telegram NEWS ANNOUNCEMENT sent to {cid}")


def send(
    parsed: dict,
    ai_result: dict,
    screenshot_url: str | None = None,
    chat_ids: list[str] | None = None,
    gamma_table_url: str | None = None,
    gamma_table_full_url: str | None = None,
    news_text: str | None = None,
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

    for cid in chat_ids:
        # Message 1: compact table, Message 2: full available observed data.
        if gamma_table_url:
            _post_with_retry(
                TELEGRAM_PHOTO_API.format(token=token),
                {"chat_id": cid, "photo": gamma_table_url, "caption": "GOLD GAMMA TABLE — Multi-Expiration"},
            )
        if gamma_table_full_url:
            _post_with_retry(
                TELEGRAM_PHOTO_API.format(token=token),
                {"chat_id": cid, "photo": gamma_table_full_url, "caption": "GOLD GAMMA TABLE — FULL DATA"},
            )
        if screenshot_url:
            _post_with_retry(
                TELEGRAM_PHOTO_API.format(token=token),
                {"chat_id": cid, "photo": screenshot_url, "caption": "QUIKSTRIKE OI — Source Screenshot"},
            )
        if news_text:
            for chunk in _chunk(news_text):
                _post_with_retry(
                    TELEGRAM_API.format(token=token),
                    {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
                )
                time.sleep(0.4)

        for text_value in messages:
            for chunk in _chunk(text_value):
                _post_with_retry(
                    TELEGRAM_API.format(token=token),
                    {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
                )
                time.sleep(0.4)
        print(f"✅ Telegram analyst bundle sent to {cid}")
