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
    status = str(ai_result.get("analysis_status") or "CONFIRMED").upper()
    bias = str(ai_result.get("bias") or "WAIT").upper()
    news = parsed.get("news_context") or []

    news_lines = []
    for item in news[:2]:
        if not isinstance(item, dict):
            continue
        headline = item.get("headline") or "-"
        source = item.get("source") or "-"
        freshness = item.get("freshness") or "UNKNOWN"
        news_lines.append(
            f"• {_escape(headline)} "
            f"<i>({_escape(source)} | {_escape(freshness)})</i>"
        )

    return "\n".join([
        "<b>GOLD MARKET</b>",
        _thai_datetime_str(),
        "",
        "<b>PRICE / REGIME</b>",
        f"Futures {_show(parsed.get('future_price'))} | CFD {_show(parsed.get('cfd_price'))}",
        f"Basis {_show(parsed.get('basis_diff'))} | DTE {_show(parsed.get('dte'))} | "
        f"<b>{_escape(ai_result.get('market_regime') or 'UNKNOWN')}</b> | "
        f"IV {_show(parsed.get('vol'))}%",
        "",
        "────────────────────────",
        "",
        "<b>MARKET READ</b>",
        _escape(ai_result.get("what") or ai_result.get("market_overview") or "-"),
        _escape(ai_result.get("why") or "-"),
        _escape(ai_result.get("positioning") or "-"),
        "",
        f"→ {_escape(ai_result.get('uncertainty') or ai_result.get('final_trade_idea') or ('Bias: ' + bias))}",
        "",
        "────────────────────────",
        "",
        "<b>WHY NOW</b>",
        _escape(ai_result.get("financial_engineering") or "-"),
        _escape(ai_result.get("positioning") or "-"),
        "",
        "<b>TECHNICAL</b>",
        _escape(ai_result.get("market_microstructure") or "-"),
        "",
        "<b>MACROECONOMIC / NEWS</b>",
        _escape(ai_result.get("macro") or "-"),
        *(news_lines or ["• ไม่มีข่าวสำคัญจากข้อมูลที่ได้รับ"]),
        "",
        "────────────────────────",
    ])


def _format_levels_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    levels = ai_result.get("levels") or {}
    scenarios = ai_result.get("scenarios") or {}
    state = raw.get("market_state") or {}
    gamma_state = state.get("gamma") or {}

    def show(value):
        return _escape(_show(value))

    return "\n".join([
        "<b>KEY LEVELS</b>",
        f"ต้านไกล  <b>{show(levels.get('resistance_far'))}</b>",
        f"Gamma Mean <b>{show(gamma_state.get('gamma_mean'))}</b>",
        f"-GEX Zone <b>{show(gamma_state.get('negative_zone'))}</b>",
        f"Trigger   <b>{show(levels.get('resistance_current'))}</b>",
        f"Support   <b>{show(levels.get('support_main'))}</b>",
        f"รับลึก    <b>{show(levels.get('support_deep'))}</b>",
        "",
        "────────────────────────",
        "",
        "<b>SCENARIO</b>",
        f"🟢 <b>BULL</b> — {_escape(scenarios.get('bull') or '-')}",
        f"🔴 <b>BEAR</b> — {_escape(scenarios.get('bear') or '-')}",
        f"🟡 <b>RANGE</b> — {_escape(scenarios.get('sideway') or '-')}",
        "",
        "────────────────────────",
    ])


def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    levels = ai_result.get("levels") or {}

    def num(key):
        value = levels.get(key)
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def fmt(value):
        return _show(value) if value is not None else "-"

    long_entry = num("resistance_current")
    long_sl = num("support_current")
    long_targets = sorted(
        [x for x in (num("resistance_main"), num("resistance_far"))
         if x is not None and long_entry is not None and x > long_entry]
    )
    short_entry = num("support_current")
    short_sl = num("resistance_current")
    short_targets = sorted(
        [x for x in (num("support_main"), num("support_deep"))
         if x is not None and short_entry is not None and x < short_entry],
        reverse=True,
    )

    trade = ai_result.get("trade_plan") or {}
    return "\n".join([
        "<b>TRADE PLAN</b>",
        "",
        "🟢 <b>LONG</b>",
        f"Trigger: {fmt(long_entry)} hold/retest",
        f"SL: &lt;{fmt(long_sl)}",
        f"TP1: {fmt(long_targets[0]) if len(long_targets) > 0 else '-'}",
        f"TP2: {fmt(long_targets[1]) if len(long_targets) > 1 else '-'}",
        "TP3: -",
        "",
        "🔴 <b>SHORT</b>",
        f"Trigger: &lt;{fmt(short_entry)} + failed retest",
        f"SL: &gt;{fmt(short_sl)}",
        f"TP1: {fmt(short_targets[0]) if len(short_targets) > 0 else '-'}",
        f"TP2: {fmt(short_targets[1]) if len(short_targets) > 1 else '-'}",
        "TP3: -",
        "",
        f"Status: <b>{_escape(str(trade.get('status') or 'CONDITIONAL').upper())}</b> | "
        f"Bias: <b>{_escape(str(ai_result.get('bias') or 'WAIT').upper())}</b>",
    ])


def format_message(parsed: dict, ai_result: dict) -> str:
    return _format_analysis_message(parsed, ai_result)


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
            detail = (response.text or "").strip()
            raise RuntimeError(f"Telegram API HTTP {response.status_code}: {detail[:500]}")
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


def _send_photo_with_fallback(token: str, chat_id: str, photo_url: str, caption: str) -> None:
    """Send a remote image; fall back to multipart upload when Telegram rejects the URL."""
    url = TELEGRAM_PHOTO_API.format(token=token)
    response = requests.post(
        url,
        json={"chat_id": chat_id, "photo": photo_url, "caption": caption},
        timeout=20,
    )
    if response.status_code < 400:
        return
    if response.status_code != 400:
        response.raise_for_status()
    try:
        image = requests.get(photo_url, timeout=20)
        image.raise_for_status()
        upload = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("image.png", image.content, image.headers.get("content-type", "image/png"))},
            timeout=30,
        )
        if upload.status_code >= 400:
            raise RuntimeError(
                f"Telegram photo upload failed HTTP {upload.status_code}: {(upload.text or '')[:500]}"
            )
    except Exception as exc:
        raise RuntimeError(
            f"Telegram photo URL rejected HTTP 400; multipart fallback failed: {exc}"
        ) from exc


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
            _send_photo_with_fallback(token, cid, gamma_table_url, "GOLD GAMMA TABLE — Multi-Expiration")
        if gamma_table_full_url:
            _send_photo_with_fallback(token, cid, gamma_table_full_url, "GOLD GAMMA TABLE — FULL DATA")
        if screenshot_url:
            _send_photo_with_fallback(token, cid, screenshot_url, "QUIKSTRIKE OI — Source Screenshot")

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

        print(f"✅ Telegram analyst bundle sent to {cid}")def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    levels = ai_result.get("levels") or {}

    def num(key):
        value = levels.get(key)
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def fmt(value):
        return _show(value) if value is not None else "-"

    long_entry = num("resistance_current")
    long_sl = num("support_current")
    long_targets = sorted(
        [x for x in (num("resistance_main"), num("resistance_far")) if x is not None and long_entry is not None and x > long_entry]
    )
    short_entry = num("support_current")
    short_sl = num("resistance_current")
    short_targets = sorted(
        [x for x in (num("support_main"), num("support_deep")) if x is not None and short_entry is not None and x < short_entry],
        reverse=True,
    )

    return "\n".join([
        "<b>TRADE PLAN</b>",
        "",
        "🟢 <b>LONG</b>",
        f"Trigger: {fmt(long_entry)} hold/retest",
        f"SL: &lt;{fmt(long_sl)}",
        f"TP1: {fmt(long_targets[0]) if len(long_targets) > 0 else '-'}",
        f"TP2: {fmt(long_targets[1]) if len(long_targets) > 1 else '-'}",
        "TP3: -",
        "",
        "🔴 <b>SHORT</b>",
        f"Trigger: &lt;{fmt(short_entry)} + failed retest",
        f"SL: &gt;{fmt(short_sl)}",
        f"TP1: {fmt(short_targets[0]) if len(short_targets) > 0 else '-'}",
        f"TP2: {fmt(short_targets[1]) if len(short_targets) > 1 else '-'}",
        "TP3: -",
        "",
        f"Status: <b>{_escape(str((ai_result.get('trade_plan') or {}).get('status') or 'CONDITIONAL').upper())}</b> | "
        f"Bias: <b>{_escape(str(ai_result.get('bias') or 'WAIT').upper())}</b>",
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
            detail = (response.text or "").strip()
            raise RuntimeError(f"Telegram API HTTP {response.status_code}: {detail[:500]}")
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


def _send_photo_with_fallback(token: str, chat_id: str, photo_url: str, caption: str) -> None:
    """Send a remote image; fall back to multipart upload when Telegram rejects the URL."""
    url = TELEGRAM_PHOTO_API.format(token=token)
    response = requests.post(
        url,
        json={"chat_id": chat_id, "photo": photo_url, "caption": caption},
        timeout=20,
    )
    if response.status_code < 400:
        return
    if response.status_code != 400:
        response.raise_for_status()
    try:
        image = requests.get(photo_url, timeout=20)
        image.raise_for_status()
        upload = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("image.png", image.content, image.headers.get("content-type", "image/png"))},
            timeout=30,
        )
        if upload.status_code >= 400:
            raise RuntimeError(
                f"Telegram photo upload failed HTTP {upload.status_code}: {(upload.text or '')[:500]}"
            )
    except Exception as exc:
        raise RuntimeError(
            f"Telegram photo URL rejected HTTP 400; multipart fallback failed: {exc}"
        ) from exc


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
            _send_photo_with_fallback(token, cid, gamma_table_url, "GOLD GAMMA TABLE — Multi-Expiration")
        if gamma_table_full_url:
            _send_photo_with_fallback(token, cid, gamma_table_full_url, "GOLD GAMMA TABLE — FULL DATA")
        if screenshot_url:
            _send_photo_with_fallback(token, cid, screenshot_url, "QUIKSTRIKE OI — Source Screenshot")

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
