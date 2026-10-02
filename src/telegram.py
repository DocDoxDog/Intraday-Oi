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


def format_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    levels = ai_result.get("levels") or {}
    scenarios = ai_result.get("scenarios") or {}
    trade = ai_result.get("trade_plan") or {}
    status = str(ai_result.get("analysis_status") or ("DEGRADED" if ai_result.get("error") else "CONFIRMED")).upper()
    bias = str(ai_result.get("bias") or "WAIT").upper()

    lines = [
        f"<b>GOLD MARKET ANALYST V2</b> • {_thai_datetime_str()}",
        f"Futures <b>{_escape(parsed.get('future_price', '-'))}</b> | CFD <b>{_escape(parsed.get('cfd_price', parsed.get('future_price', '-')))}</b> | DTE {_escape(parsed.get('dte', '-'))}",
        f"Status: <b>{_escape(status)}</b> | Bias: <b>{_escape(bias)}</b>",
        "",
        "<b>WHAT</b>",
        _escape(_compact(ai_result.get("what") or ai_result.get("market_overview"), 700)),
        "",
        "<b>WHY</b>",
        _escape(_compact(ai_result.get("why"), 700)),
        "",
        "<b>POSITIONING</b>",
        _escape(_compact(ai_result.get("positioning"), 700)),
        "",
        "<b>KEY LEVELS</b>",
    ]
    for key, label in (
        ("resistance_far","ต้านไกล"),("resistance_main","ต้านหลัก"),
        ("resistance_current","ต้านใกล้"),("support_current","รับใกล้"),
        ("support_main","รับหลัก"),("support_deep","รับลึก")
    ):
        value = levels.get(key)
        lines.append(f"{label}: <b>{_escape(value if value is not None else 'UNKNOWN')}</b>")

    if gamma.get("expiration_count"):
        lines += [
            "",
            "<b>GAMMA TERM STRUCTURE</b>",
            _escape(f"{gamma.get('expiration_count')} expirations | +GEX zone {zones.get('highest_positive_gamma') or 'UNKNOWN'} | -GEX zone {zones.get('highest_negative_gamma') or 'UNKNOWN'}"),
        ]

    lines += [
        "",
        "<b>SCENARIOS</b>",
        f"🟢 Bull — {_escape(_compact(scenarios.get('bull'), 500))}",
        f"🔴 Bear — {_escape(_compact(scenarios.get('bear'), 500))}",
        f"🟡 Sideway — {_escape(_compact(scenarios.get('sideway'), 500))}",
        "",
        "<b>TRADE PLAN</b>",
        f"Status: <b>{_escape(trade.get('status') or 'NO_TRADE')}</b>",
        _escape(_compact(trade.get('setup'), 500)),
        f"Confirmation: {_escape(_compact(trade.get('confirmation'), 500))}",
        f"Invalidation: {_escape(_compact(trade.get('invalidation'), 500))}",
        f"Risk: {_escape(_compact(trade.get('risk_note'), 500))}",
    ]
    limitations = ai_result.get("data_limitations") or []
    if limitations:
        lines += ["", "<b>DATA LIMITATIONS</b>"] + ["• " + _escape(_compact(x, 260)) for x in limitations[:4]]
    refs = ai_result.get("evidence_refs") or []
    if refs:
        lines += ["", f"<i>Evidence: {_escape(', '.join(map(str, refs)))}</i>"]
    return "\n".join(lines)

def format_notification(parsed: dict, ai_result: dict) -> str:
    if "error" in ai_result:
        return f"⚠️ OI ANALYST\n{_compact(ai_result['error'], 500)}"

    bias = str(ai_result.get("bias") or ai_result.get("short_bias") or "WAIT").upper()
    headline = _compact(ai_result.get("market_overview"), 900)
    watch = _compact(ai_result.get("sideway_case"), 420)

    return (
        f"🟡 <b>GOLD OI UPDATE</b>  •  {_thai_datetime_str()}\n"
        f"Bias: <b>{_escape(bias)}</b>\n\n"
        f"{_escape(headline)}\n\n"
        f"<b>Next watch</b>\n{_escape(watch)}"
    )

