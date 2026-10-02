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
    status = str(ai_result.get("analysis_status") or "CONFIRMED").upper()
    bias = str(ai_result.get("bias") or "WAIT").upper()
    raw = parsed.get("raw_series") or {}
    technical = parsed.get("technical_context") or {}
    confirmation = technical.get("confirmation") or {}

    lines = [
        "<b>🧭 GOLD • มองตลาดตอนนี้</b>",
        f"ราคา CFD <b>{_escape(parsed.get('cfd_price', parsed.get('future_price', '-')))}</b> · Bias <b>{_escape(bias)}</b>",
        "",
        "<b>เกิดอะไรขึ้น</b>",
        _escape(_compact(ai_result.get("what") or ai_result.get("market_overview"), 850)),
        "",
        "<b>ทำไมถึงสำคัญ</b>",
        _escape(_compact(ai_result.get("why"), 850)),
        "",
        "<b>โครงสร้างตลาด</b>",
        _escape(_compact(ai_result.get("positioning"), 850)),
    ]

    if confirmation:
        lines += [
            "",
            "<b>Price / Technical Context</b>",
            _escape(
                _compact(
                    f"H4={confirmation.get('bias','UNKNOWN')} | "
                    f"HTF aligned={confirmation.get('htf_aligned','UNKNOWN')} | "
                    f"M15/M5 aligned={confirmation.get('m15_m5_aligned','UNKNOWN')}",
                    500,
                )
            ),
        ]

    levels = ai_result.get("levels") or {}
    shown = [
        ("resistance_current", "ต้านใกล้"),
        ("resistance_main", "ต้านหลัก"),
        ("support_current", "รับใกล้"),
        ("support_main", "รับหลัก"),
    ]
    level_lines = [
        f"{label}: <b>{_escape(levels.get(key) if levels.get(key) is not None else 'UNKNOWN')}</b>"
        for key, label in shown
    ]
    lines += ["", "<b>จุดที่ต้องดู</b>"] + level_lines

    limitations = ai_result.get("data_limitations") or []
    if limitations:
        lines += ["", "<b>สิ่งที่ยังไม่ชัด</b>"] + ["• " + _escape(_compact(x, 300)) for x in limitations[:3]]

    return "\n".join(lines)


def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    trade = ai_result.get("trade_plan") or {}
    direction = str(trade.get("direction") or "WAIT").upper()
    status = str(trade.get("status") or "NO_TRADE").upper()

    lines = [
        "<b>🎯 GOLD • TRADE PLAN</b>",
        f"สถานะ: <b>{_escape(status)}</b> · ทิศทาง: <b>{_escape(direction)}</b>",
        "",
        f"<b>Entry</b>   {_escape(trade.get('entry') or 'UNKNOWN')}",
        f"<b>SL</b>      {_escape(trade.get('stop_loss') or 'UNKNOWN')}",
        f"<b>TP1</b>     {_escape(trade.get('take_profit_1') or 'UNKNOWN')}",
        f"<b>TP2</b>     {_escape(trade.get('take_profit_2') or 'UNKNOWN')}",
        "",
        "<b>Setup</b>",
        _escape(_compact(trade.get("setup"), 650)),
        "",
        "<b>Trigger</b>",
        _escape(_compact(trade.get("trigger"), 650)),
        "",
        "<b>Invalidation</b>",
        _escape(_compact(trade.get("invalidation"), 650)),
        "",
        "<b>เหตุผล</b>",
        _escape(_compact(trade.get("confirmation"), 650)),
        "",
        "<b>Risk</b>",
        _escape(_compact(trade.get("risk_note"), 500)),
    ]
    return "\n".join(lines)


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

    source_text = _format_source_message(parsed)
    analysis_text = _format_analysis_message(parsed, ai_result)
    trade_text = _format_trade_plan_message(parsed, ai_result)

    for cid in chat_ids:
        photos = [url for url in (gamma_table_url, screenshot_url) if url]
        if len(photos) >= 2:
            media = [
                {"type": "photo", "media": gamma_table_url, "caption": "GOLD GAMMA TABLE • 7 DAYS"},
                {"type": "photo", "media": screenshot_url, "caption": "QUIKSTRIKE OI • SOURCE"},
            ]
            _post_with_retry(
                f"https://api.telegram.org/bot{token}/sendMediaGroup",
                {"chat_id": cid, "media": media},
            )
        else:
            if gamma_table_url:
                _post_with_retry(
                    TELEGRAM_PHOTO_API.format(token=token),
                    {"chat_id": cid, "photo": gamma_table_url, "caption": "GOLD GAMMA TABLE • 7 DAYS"},
                )
            if screenshot_url:
                _post_with_retry(
                    TELEGRAM_PHOTO_API.format(token=token),
                    {"chat_id": cid, "photo": screenshot_url, "caption": "QUIKSTRIKE OI • SOURCE"},
                )

        for text in (source_text, analysis_text, trade_text):
            for chunk in _chunk(text):
                _post_with_retry(
                    TELEGRAM_API.format(token=token),
                    {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
                )
                time.sleep(0.4)
        print(f"✅ Telegram 3-message analyst bundle sent to {cid}")
