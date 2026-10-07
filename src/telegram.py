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
    """Render human-readable support/resistance only.

    Gamma/scenario calculations remain available internally; Telegram keeps this
    section focused on the price map a trader needs at a glance.
    """
    market_map = ai_result.get("market_map") or {}
    trade = ai_result.get("trade_plan") or {}

    # Legacy snapshots may only contain the old trade-plan fields.
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
        }

    def show(value):
        return _escape(_show(value))

    long_trigger = market_map.get("long_trigger")
    short_trigger = market_map.get("short_trigger")
    long_role = str((market_map.get("roles") or {}).get("long_trigger") or "").upper()
    short_role = str((market_map.get("roles") or {}).get("short_trigger") or "").upper()

    if long_trigger is not None and short_trigger is not None and long_trigger == short_trigger:
        trigger_line = f"จุดเปลี่ยน: {show(long_trigger)} — ยืนเหนือ = มองขึ้น / รีเทสต์ไม่ผ่าน = มองลง"
    else:
        parts = []
        if long_trigger is not None:
            parts.append(f"ขึ้น: {show(long_trigger)}")
        if short_trigger is not None:
            parts.append(f"ลง: {show(short_trigger)}")
        trigger_line = "จุดเปลี่ยน: " + (" | ".join(parts) if parts else "ยังไม่มี")

    lines = [
        "<b>KEY LEVELS</b>",
        f"แนวต้าน: R1 {show(market_map.get('R1'))} | R2 {show(market_map.get('R2'))} | R3 {show(market_map.get('R3'))}",
        f"แนวรับ: R? " + show(None) if False else f"แนวรับ: S1 {show(market_map.get('S1'))} | S2 {show(market_map.get('S2'))} | S3 {show(market_map.get('S3'))}",
        trigger_line,
    ]
    return "\n".join(lines)


def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    """Render a trader-friendly plan: entry condition, SL and TP."""
    trade = ai_result.get("trade_plan") or {}
    execution = trade.get("execution_plan") or {}

    # Backward-compatible adapter for legacy snapshots.
    if not execution:
        execution = {
            "state": trade.get("execution_state") or trade.get("status") or "DATA_INSUFFICIENT",
            "long": {
                "state": trade.get("long_state") or ("ARMED" if trade.get("long_trigger") is not None else "DATA_INSUFFICIENT"),
                "trigger": trade.get("long_trigger"),
                "stop": trade.get("long_stop"),
                "targets": [x for x in (trade.get("long_tp1"), trade.get("long_tp2"), trade.get("long_tp3")) if x is not None],
            },
            "short": {
                "state": trade.get("short_state") or ("ARMED" if trade.get("short_trigger") is not None else "DATA_INSUFFICIENT"),
                "trigger": trade.get("short_trigger"),
                "stop": trade.get("short_stop"),
                "targets": [x for x in (trade.get("short_tp1"), trade.get("short_tp2"), trade.get("short_tp3")) if x is not None],
            },
        }

    def fmt(value):
        return _escape(_show(value))

    def preferred_label(side: str) -> str:
        bias = str(ai_result.get("bias") or "").upper()
        if side == "SHORT" and bias in {"SELL", "SHORT_CONDITIONAL", "BEARISH"}:
            return "แผนหลัก"
        if side == "LONG" and bias in {"BUY", "LONG_CONDITIONAL", "BULLISH"}:
            return "แผนหลัก"
        return "แผนสำรอง"

    def render_side(label: str, emoji: str, payload: dict) -> list[str]:
        trigger = payload.get("trigger")
        stop = payload.get("stop")
        targets = [x for x in (payload.get("targets") or []) if x is not None]
        state = str(payload.get("state") or "DATA_INSUFFICIENT").upper()
        lines = [f"{emoji} <b>{label} — {preferred_label(label)}</b>"]

        if trigger is None or stop is None:
            lines.append("ยังไม่มีจุดเข้า/SL ที่ข้อมูลรองรับครบ")
            return lines

        if label == "SHORT":
            lines.append(f"เข้า: ราคาเด้งกลับทดสอบ {fmt(trigger)} แล้วไม่ผ่าน พร้อม M15/M5 ยืนยันลง")
        else:
            lines.append(f"เข้า: ราคาเบรกและยืนเหนือ {fmt(trigger)} พร้อม M15/M5 ยืนยันขึ้น")

        lines.append(f"SL: {fmt(stop)}")

        if targets:
            lines.append("TP: " + " → ".join(fmt(x) for x in targets[:3]))
        else:
            lines.append("TP: ยังไม่มีระดับที่คุ้มความเสี่ยง")

        if state in {"TRIGGERED_WAIT_CONFIRMATION", "TRIGGERED_WAIT_RISK_REWARD"}:
            lines.append("สถานะ: ราคาเข้าโซนแล้ว แต่ยังรอการยืนยัน")
        elif state == "CONFIRMED":
            lines.append("สถานะ: เงื่อนไขครบตามระบบ")
        elif state == "ARMED":
            lines.append("สถานะ: รอจังหวะเข้า")
        return lines

    overall = str(execution.get("state") or trade.get("status") or "UNKNOWN").upper()
    bias = str(ai_result.get("bias") or trade.get("direction") or "WAIT").upper()

    status_text = {
        "CONFIRMED": "ยืนยันแล้ว",
        "TRIGGERED": "เข้าโซนแล้ว รอยืนยัน",
        "ARMED": "รอจังหวะ",
        "DATA_INSUFFICIENT": "ข้อมูลไม่พอ",
    }.get(overall, overall)

    lines = [
        "<b>TRADE PLAN</b>",
        f"มุมมอง: <b>{_escape(bias)}</b> | สถานะ: <b>{_escape(status_text)}</b>",
        "",
    ]
    lines.extend(render_side("LONG", "🟢", execution.get("long") or {}))
    lines += ["",]
    lines.extend(render_side("SHORT", "🔴", execution.get("short") or {}))
    lines += [
        "",
        "หมายเหตุ: แผนนี้เป็น conditional plan; OI/ΔOI/GEX ใช้เป็นบริบท ไม่ใช่หลักฐานว่า dealer อยู่ฝั่งใด และระบบนี้ไม่ส่งคำสั่ง",
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

        # Keep the full analyst bundle: Market Analysis -> Key Levels/Scenario -> Trade Plan.
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
