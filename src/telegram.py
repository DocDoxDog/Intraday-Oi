"""Telegram delivery and presentation for the GOLD Market Analyst."""

from __future__ import annotations

import html
import os
import re
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
    raw = parsed.get("raw_series") or {}
    market_state = raw.get("market_state") or {}
    flow = market_state.get("flow") or {}
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
        "<b>OI POSITIONING</b>",
        f"Current OI   Put {_show(flow.get('oi_put'), 0)} | Call {_show(flow.get('oi_call'), 0)} | Total {_show(flow.get('oi_total'), 0)}",
        f"EOD OI       Put {_show(flow.get('eod_oi_put'), 0)} | Call {_show(flow.get('eod_oi_call'), 0)} | Total {_show(flow.get('eod_oi_total'), 0)}",
        f"OI CHANGE    Put {_show(flow.get('oi_change_put'), 0)} | Call {_show(flow.get('oi_change_call'), 0)} | Total {_show(flow.get('oi_change_total'), 0)}",
        f"ΔOI vs EOD   Put {_show(flow.get('delta_oi_put'), 0)} | Call {_show(flow.get('delta_oi_call'), 0)} | Total {_show(flow.get('delta_oi_total'), 0)}",
        f"CHURN        Put {_show(flow.get('source_churn_put'), 2)} | Call {_show(flow.get('source_churn_call'), 2)} | Total {_show(flow.get('source_churn_total'), 2)}",
        "",
        "────────────────────────",
        "",
        "<b>MARKET READ</b>",
        f"Status: <b>{_escape(status)}</b> | Bias: <b>{_escape(bias)}</b>",
        _escape(ai_result.get("what") or ai_result.get("market_overview") or "-"),
        _escape(ai_result.get("why") or "-"),
        _escape(ai_result.get("positioning") or "-"),
        "",
        f"→ {_escape(ai_result.get('final_trade_idea') if isinstance(ai_result.get('final_trade_idea'), str) and ai_result.get('final_trade_idea').strip() else ('Bias: ' + bias))}",
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
        _escape(ai_result.get("macro") or "ไม่มี Macro/News evidence ที่เพียงพอ"),
        "",
        "────────────────────────",
    ])


def _format_levels_message(parsed: dict, ai_result: dict) -> str:
    """Render the canonical market map; never manufacture fallback execution levels."""
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    levels = ai_result.get("levels") or {}
    scenarios = ai_result.get("scenarios") or {}
    state = raw.get("market_state") or {}
    gamma_state = state.get("gamma") or {}
    gamma_zones = raw.get("multi_expiry_gamma_zones") or {}
    trade = ai_result.get("trade_plan") or {}
    market_map = ai_result.get("market_map") or {}

    def show(value):
        return _escape(_show(value))

    # Backward-compatible adapter for direct renderer callers. It only maps
    # already-supplied validated trade fields; it never creates a price.
    if not market_map:
        market_map = {
            "R3": trade.get("long_tp3"),
            "R2": trade.get("long_tp2"),
            "R1": trade.get("long_tp1"),
            "long_trigger": trade.get("long_trigger"),
            "short_trigger": trade.get("short_trigger"),
            "S1": trade.get("short_tp1"),
            "S2": trade.get("short_tp2"),
            "S3": trade.get("short_tp3"),
            "long_status": "CONDITIONAL" if all(trade.get(k) is not None for k in ("long_trigger","long_stop","long_tp1","long_tp2","long_tp3")) else "NO_TRADE",
            "short_status": "CONDITIONAL" if all(trade.get(k) is not None for k in ("short_trigger","short_stop","short_tp1","short_tp2","short_tp3")) else "NO_TRADE",
        }
    long_trigger = market_map.get("long_trigger")
    short_trigger = market_map.get("short_trigger")

    return "\n".join([
        "<b>KEY LEVELS — แผนที่ราคา</b>",
        f"R3  {show(market_map.get('R3'))}",
        f"R2  {show(market_map.get('R2'))}",
        f"R1  {show(market_map.get('R1'))}",
        f"🟢 <b>LONG TRIGGER</b>  &gt; {show(long_trigger)}",
        f"Positive Gamma Zone  {show(gamma_state.get('positive_zone') if gamma_state.get('positive_zone') is not None else gamma_zones.get('highest_positive_gamma'))}",
        f"Gamma Mean  {show(gamma_state.get('gamma_mean'))}",
        f"Negative GEX Zone  {show(gamma_state.get('negative_zone') if gamma_state.get('negative_zone') is not None else gamma_zones.get('highest_negative_gamma'))}",
        f"🔴 <b>SHORT TRIGGER</b> &lt; {show(short_trigger)}",
        f"S1  {show(market_map.get('S1'))}",
        f"S2  {show(market_map.get('S2'))}",
        f"S3  {show(market_map.get('S3'))}",
        "",
        f"LONG: <b>{_escape(market_map.get('long_status') or 'NO_TRADE')}</b> | SHORT: <b>{_escape(market_map.get('short_status') or 'NO_TRADE')}</b>",
        "",
        "<b>GAMMA TERM STRUCTURE</b>",
        f"<b>{len(gamma.get('columns') or [])}</b> expirations",
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
    """Render the same canonical map used by KEY LEVELS and SCENARIO."""
    trade = ai_result.get("trade_plan") or {}
    market_map = ai_result.get("market_map") or {}
    # Backward-compatible adapter for direct renderer tests/callers that pass
    # an already validated trade_plan. This does not invent any price.
    if not market_map:
        market_map = {
            "R3": trade.get("long_tp3"),
            "R2": trade.get("long_tp2"),
            "R1": trade.get("long_tp1"),
            "long_trigger": trade.get("long_trigger"),
            "short_trigger": trade.get("short_trigger"),
            "S1": trade.get("short_tp1"),
            "S2": trade.get("short_tp2"),
            "S3": trade.get("short_tp3"),
            "long_status": "CONDITIONAL" if all(trade.get(k) is not None for k in ("long_trigger","long_stop","long_tp1","long_tp2","long_tp3")) else "NO_TRADE",
            "short_status": "CONDITIONAL" if all(trade.get(k) is not None for k in ("short_trigger","short_stop","short_tp1","short_tp2","short_tp3")) else "NO_TRADE",
        }

    def fmt(value):
        return _escape(_show(value))

    long_ok = str(market_map.get("long_status") or "NO_TRADE").upper() == "CONDITIONAL"
    short_ok = str(market_map.get("short_status") or "NO_TRADE").upper() == "CONDITIONAL"

    lines = [
        "<b>TRADE PLAN</b>",
        "",
        "🟢 <b>LONG — แผนฝั่งขึ้น</b>",
    ]
    if long_ok:
        lines += [
            f"เข้าเมื่อ: เบรกเหนือ {fmt(market_map.get('long_trigger'))} แล้วกลับมาทดสอบและยืนได้",
            f"ยกเลิกแผนเมื่อ: หลุด {fmt(trade.get('long_stop'))}",
            f"เป้าหมาย 1: {fmt(market_map.get('R1'))}",
            f"เป้าหมาย 2: {fmt(market_map.get('R2'))}",
            f"เป้าหมาย 3: {fmt(market_map.get('R3'))}",
        ]
    else:
        lines.append("NO_TRADE — ระดับฝั่งขึ้นไม่ครบหรือไม่ผ่าน validation")

    lines += ["", "🔴 <b>SHORT — แผนฝั่งลง</b>"]
    if short_ok:
        lines += [
            f"เข้าเมื่อ: หลุด {fmt(market_map.get('short_trigger'))} แล้วรีเทสต์ไม่ผ่าน",
            f"ยกเลิกแผนเมื่อ: กลับเหนือ {fmt(trade.get('short_stop'))}",
            f"เป้าหมาย 1: {fmt(market_map.get('S1'))}",
            f"เป้าหมาย 2: {fmt(market_map.get('S2'))}",
            f"เป้าหมาย 3: {fmt(market_map.get('S3'))}",
        ]
    else:
        lines.append("NO_TRADE — ระดับฝั่งลงไม่ครบหรือไม่ผ่าน validation")

    lines += [
        "",
        f"Status: <b>{_escape(str(trade.get('status') or 'NO_TRADE').upper())}</b> | "
        f"Bias: <b>{_escape(str(ai_result.get('bias') or 'WAIT').upper())}</b>",
    ]
    return "\n".join(lines)


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
            # Telegram HTML parsing is strict. If a dynamic field ever slips
            # through the renderer, preserve delivery by retrying that message
            # as plain text rather than losing the entire analyst bundle.
            if response.status_code == 400 and payload.get("parse_mode") == "HTML":
                plain_payload = dict(payload)
                plain_payload.pop("parse_mode", None)
                plain_payload["text"] = re.sub(r"<[^>]*>", "", str(plain_payload.get("text") or ""))
                fallback = requests.post(url, json=plain_payload, timeout=timeout)
                if fallback.status_code < 400:
                    return
                detail = (fallback.text or detail).strip()
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
