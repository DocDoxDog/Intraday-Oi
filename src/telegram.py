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
    if "error" in ai_result:
        return f"<b>OI ANALYST</b>\n{_escape(_compact(ai_result['error'], 700))}"

    raw = parsed.get("raw_series") or {}
    gex = raw.get("gex") or {}
    levels = {
        "ต้านไกล": ai_result.get("resistance_far"),
        "ต้านหลัก": ai_result.get("resistance_main"),
        "ต้านใกล้": ai_result.get("resistance_current"),
        "รับใกล้": ai_result.get("support_current"),
        "รับหลัก": ai_result.get("support_main"),
        "รับลึก": ai_result.get("support_deep"),
    }

    bias = str(ai_result.get("bias") or ai_result.get("short_bias") or "WAIT").upper()
    uncertainty = ai_result.get("uncertainty")
    uncertainty_text = f" | uncertainty {_escape(uncertainty)}" if uncertainty is not None else ""

    lines = [
        f"<b>GOLD OI ANALYST</b>  •  {_thai_datetime_str()}",
        f"Futures <b>{_escape(parsed.get('future_price', '-'))}</b>"
        f"  |  CFD <b>{_escape(parsed.get('cfd_price', parsed.get('future_price', '-')))}</b>"
        f"  |  DTE {_escape(parsed.get('dte', '-'))}",
        "",
        "<b>Market read</b>",
        _escape(_compact(ai_result.get("market_overview"), 850)),
        "",
        "<b>Why it matters</b>",
        _escape(
            _compact(
                ai_result.get("bull_case"),
                420,
            )
        ),
        "",
        "<b>Key levels</b>",
    ]

    for name, value in levels.items():
        lines.append(f"{name}: <b>{_escape(_compact(value, 220))}</b>")

    lines += [
        "",
        "<b>Scenarios</b>",
        f"🟢 Bull — {_escape(_compact(ai_result.get('bull_case'), 520))}",
        f"🔴 Bear — {_escape(_compact(ai_result.get('bear_case'), 520))}",
        f"🟡 Sideway — {_escape(_compact(ai_result.get('sideway_case'), 520))}",
        "",
        f"<b>Bias:</b> <b>{bias}</b>{uncertainty_text}",
    ]

    limitations = ai_result.get("data_limitations") or []
    if limitations:
        lines += [
            "",
            "<b>ข้อมูลที่ต้องระวัง</b>",
            "• " + "\n• ".join(_escape(_compact(x, 260)) for x in limitations[:3]),
        ]

    refs = ai_result.get("evidence_refs") or []
    if refs:
        lines += ["", f"<i>Evidence: {_escape(', '.join(map(str, refs)))}</i>"]

    # Mention deterministic GEX state without dumping the entire strike table.
    if gex.get("status") == "ok":
        gex_state = []
        if gex.get("gamma_flip") is not None:
            gex_state.append(f"gamma flip {_escape(gex['gamma_flip'])}")
        if gex.get("call_wall") is not None:
            gex_state.append(f"call wall {_escape(gex['call_wall'])}")
        if gex.get("put_wall") is not None:
            gex_state.append(f"put wall {_escape(gex['put_wall'])}")
        if gex_state:
            lines.insert(7, "<i>" + " • ".join(gex_state) + "</i>")

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
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ไม่ได้ตั้งค่า")

    if chat_ids is None:
        raw_ids = os.environ.get("TELEGRAM_CHAT_ID", "")
        chat_ids = [cid.strip() for cid in raw_ids.split(",") if cid.strip()]

    if not chat_ids:
        raise RuntimeError("ไม่มี chat_ids ให้ส่ง")

    detailed = format_message(parsed, ai_result)
    notification = format_notification(parsed, ai_result)

    for cid in chat_ids:
        if screenshot_url:
            try:
                _post_with_retry(
                    TELEGRAM_PHOTO_API.format(token=token),
                    {"chat_id": cid, "photo": screenshot_url},
                )
            except Exception as exc:
                print(f"⚠️ Telegram photo failed for {cid}: {exc}")

        for chunk in _chunk(detailed):
            _post_with_retry(
                TELEGRAM_API.format(token=token),
                {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
            )
            time.sleep(0.4)

        _post_with_retry(
            TELEGRAM_API.format(token=token),
            {"chat_id": cid, "text": notification, "parse_mode": "HTML"},
        )
        print(f"✅ Telegram analyst update sent to {cid}")
