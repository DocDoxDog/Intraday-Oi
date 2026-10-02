"""Telegram delivery and presentation for the GOLD Market Analyst."""

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


def _escape(value: object) -> str:
    return html.escape(str(value or "-"), quote=False)


def _show(value: object, digits: int = 2) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, (int, float)):
        return f"{float(value):,.{digits}f}"
    text = str(value).strip()
    try:
        return f"{float(text):,.{digits}f}"
    except ValueError:
        return text


def _text(value: object) -> str:
    return str(value or "-").strip()


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


def _format_analysis_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    news = parsed.get("news_context") or []
    status = str(ai_result.get("analysis_status") or "CONFIRMED").upper()
    bias = str(ai_result.get("bias") or "WAIT").upper()

    lines = [
        "<b>GOLD MARKET ANALYST V2</b>",
        _thai_datetime_str(),
        f"<b>Futures</b> {_show(parsed.get('future_price'))}  |  "
        f"<b>CFD</b> {_show(parsed.get('cfd_price'))}  |  "
        f"<b>Basis</b> {_show(parsed.get('basis_diff'))} (FUTURES - CFD)",
        f"<b>DTE</b> {_show(parsed.get('dte'))}  |  "
        f"<b>Status</b> {status}  |  <b>Bias</b> {bias}",
        "",
        "<b>MARKET STATE</b>",
        f"<b>Regime:</b> {_escape(ai_result.get('market_regime') or 'UNKNOWN')}",
        _escape(ai_result.get("what") or ai_result.get("market_overview") or "-"),
        "",
        "<b>DRIVERS</b>",
        f"<b>Macro:</b> {_escape(ai_result.get('macro') or '-')}",
        f"<b>Financial Engineering:</b> {_escape(ai_result.get('financial_engineering') or '-')}",
        f"<b>Microstructure:</b> {_escape(ai_result.get('market_microstructure') or '-')}",
        f"<b>Psychology:</b> {_escape(ai_result.get('market_psychology') or '-')}",
        "",
        "<b>WHY / POSITIONING</b>",
        _escape(ai_result.get("why") or "-"),
        _escape(ai_result.get("positioning") or "-"),
        "",
        "<b>FLOW & HISTORY</b>",
        f"OI  Put {_show(totals.get('open_interest_view_put', totals.get('open_interest_put')))}"
        f"  |  Call {_show(totals.get('open_interest_view_call', totals.get('open_interest_call')))}"
        f"  |  Total {_show(totals.get('open_interest_view_total', totals.get('open_interest_total')))}",
        f"OI Change  Put {_show(totals.get('oi_change_put'))}"
        f"  |  Call {_show(totals.get('oi_change_call'))}"
        f"  |  Total {_show(totals.get('oi_change_total'))}",
        f"ΔOI vs baseline  Put {_show(totals.get('oi_delta_put'))}"
        f"  |  Call {_show(totals.get('oi_delta_call'))}"
        f"  |  Total {_show(totals.get('oi_delta_total'))}",
        f"Churn  Put {_show(totals.get('quikstrike_churn_put'))}"
        f"  |  Call {_show(totals.get('quikstrike_churn_call'))}"
        f"  |  Total {_show(totals.get('churn'))}",
        f"IV {_show(parsed.get('vol'))}%  |  IV Δ {_show(parsed.get('vol_chg'))}%",
        _escape(ai_result.get("history_comparison") or "-"),
    ]

    if news:
        lines += ["", "<b>NEWS CONTEXT</b>"]
        for item in news[:2]:
            headline = item.get("headline") or "-"
            source = item.get("source") or "-"
            published = item.get("published_at") or "-"
            lines.append(
                f"• <b>{_escape(headline)}</b>\n"
                f"  {_escape(source)} | {_escape(published)}"
            )

    return "\n".join(lines)


def _format_levels_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    levels = ai_result.get("levels") or {}
    scenarios = ai_result.get("scenarios") or {}

    def show(value):
        return _escape(_show(value))

    return "\n".join([
        "<b>KEY LEVELS (CFD)</b>",
        f"🔴 ต้านไกล: <b>{show(levels.get('resistance_far'))}</b>",
        f"🔴 ต้านหลัก: <b>{show(levels.get('resistance_main'))}</b>",
        f"🟠 ต้านใกล้: <b>{show(levels.get('resistance_current'))}</b>",
        f"🟢 รับใกล้: <b>{show(levels.get('support_current'))}</b>",
        f"🟢 รับหลัก: <b>{show(levels.get('support_main'))}</b>",
        f"🟢 รับลึก: <b>{show(levels.get('support_deep'))}</b>",
        "",
        "<b>GAMMA TERM STRUCTURE</b>",
        f"<b>{len(gamma.get('columns') or [])}</b> expirations"
        f"  |  +GEX zone <b>{show(zones.get('highest_positive_gamma'))}</b>"
        f"  |  -GEX zone <b>{show(zones.get('highest_negative_gamma'))}</b>",
        "",
        "<b>SCENARIOS</b>",
        f"🟢 <b>Bull</b> — {_escape(scenarios.get('bull') or '-')}",
        f"🔴 <b>Bear</b> — {_escape(scenarios.get('bear') or '-')}",
        f"🟡 <b>Sideway</b> — {_escape(scenarios.get('sideway') or '-')}",
        "",
        "<b>CASE MAP</b>",
        f"<b>BASE</b> — {_escape(ai_result.get('base_case') or '-')}",
        f"<b>ALT</b> — {_escape(ai_result.get('alternative_case') or '-')}",
        f"<b>INVALIDATION</b> — {_escape(ai_result.get('invalidation_case') or '-')}",
    ])


def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    trade = ai_result.get("trade_plan") or {}
    return "\n".join([
        "<b>TRADE PLAN</b>",
        f"Status: {_escape(str(trade.get('status') or 'CONDITIONAL').upper())}",
        f"<b>Direction:</b> {_escape(trade.get('direction') or 'WAIT')}",
        f"<b>Entry:</b> {_escape(trade.get('entry') or 'UNKNOWN')}",
        f"<b>Stop:</b> {_escape(trade.get('stop_loss') or 'UNKNOWN')}",
        f"<b>TP1:</b> {_escape(trade.get('take_profit_1') or 'UNKNOWN')}",
        f"<b>TP2:</b> {_escape(trade.get('take_profit_2') or 'UNKNOWN')}",
        "",
        f"<b>Trigger:</b> {_escape(trade.get('trigger') or 'UNKNOWN')}",
        f"<b>Invalidation:</b> {_escape(trade.get('invalidation') or 'UNKNOWN')}",
        f"<b>Risk/Reward:</b> {_escape(trade.get('risk_reward') or 'UNKNOWN')}",
        f"<b>Market Condition:</b> {_escape(trade.get('market_condition') or 'UNKNOWN')}",
        f"<b>Position Risk:</b> {_escape(trade.get('position_risk') or 'UNKNOWN')}",
        f"<b>Risk:</b> {_escape(trade.get('risk_note') or 'UNKNOWN')}",
        "",
        "<b>FINAL TRADE IDEA</b>",
        _escape(ai_result.get('final_trade_idea') or trade.get('setup') or 'UNKNOWN'),
    ])


def format_message(parsed: dict, ai_result: dict) -> str:
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
    for cid in [str(x).strip() for x in chat_ids if str(x).strip()]:
        for chunk in _chunk(news_text):
            _post_with_retry(
                TELEGRAM_API.format(token=token),
                {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
            )
        print(f"✅ Telegram NEWS ANNOUNCEMENT sent to {cid}")


def send(
    parsed: dict,
    ai_result: dict,
    screenshot_url: str | None = None,
    chat_ids: list[str] | None = None,
    gamma_table_url: str | None = None,
    gamma_table_full_url: str | None = None,
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ไม่ได้ตั้งค่า")
    if chat_ids is None:
        raise RuntimeError("ต้องระบุ chat_ids ที่ผ่านการอนุมัติจาก customer registry")
    chat_ids = [str(cid).strip() for cid in chat_ids if str(cid).strip()]
    if not chat_ids:
        raise RuntimeError("ไม่มี authorized chat_ids ให้ส่ง")

    for cid in chat_ids:
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

        for message in (
            _format_analysis_message(parsed, ai_result),
            _format_levels_message(parsed, ai_result),
            _format_trade_plan_message(parsed, ai_result),
        ):
            for chunk in _chunk(message):
                _post_with_retry(
                    TELEGRAM_API.format(token=token),
                    {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
                )
                time.sleep(0.25)

        print(f"✅ Telegram analyst bundle sent to {cid}")
