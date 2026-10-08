"""Telegram delivery and presentation for the GOLD Market Analyst."""

from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from src.customer_narrative import build_customer_narrative


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
    """Render analysis first; raw OI/vol numbers stay as supporting evidence."""
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    decision = state.get("decision") or {}
    status = str(decision.get("analysis_status") or state.get("analysis_status") or "DEVELOPING").upper()
    bias = str(decision.get("structural_bias") or ai_result.get("bias") or "WAIT").upper()
    narrative = build_customer_narrative(parsed, ai_result)

    return "\n".join([
        "<b>GOLD MARKET</b>",
        _thai_datetime_str(),
        "",
        "<b>PRICE / REGIME</b>",
        f"Futures {_show(parsed.get('future_price'))} | CFD {_show(parsed.get('cfd_price'))}",
        f"Basis {_show(parsed.get('basis_diff'))} | DTE {_show(parsed.get('dte'))} | "
        f"<b>{_escape(_friendly_regime(state, ai_result))}</b>",
        "",
        "<b>MARKET READ</b>",
        f"สถานะ: <b>{_escape(status)}</b> | มุมมอง: <b>{_escape(_friendly_bias(bias))}</b>",
        _escape(narrative["market_read"]),
        "",
        "<b>VOLATILITY — ตลาดกำลังผันผวนแค่ไหน</b>",
        _escape(narrative["volatility"]),
        "",
        "<b>OI POSITIONING — ผู้เล่นกำลังเพิ่ม/ลดสถานะอย่างไร</b>",
        _escape(narrative["oi_positioning"]),
        "",
        "<b>FLOW STATEMENT — ภาพรวมแรงที่กำลังเกิดขึ้น</b>",
        _escape(narrative["flow_statement"]),
        "",
        "<b>CONFIRMATION — ตอนนี้ยืนยันทางไหนแล้ว</b>",
        _escape(narrative["confirmation"]),
        "",
        "<b>WHY NOW — ทำไมต้องจับตาตอนนี้</b>",
        _escape(narrative["why_now"]),
        "",
        "<b>TECHNICAL</b>",
        _escape(narrative["technical"]),
        "",
        "<b>MACROECONOMIC / NEWS</b>",
        _escape(narrative["macro_news"]),
        "",
        "หมายเหตุ: ตัวเลข OI / IV / Gamma เป็นหลักฐานประกอบการวิเคราะห์ ไม่ใช่สัญญาณซื้อขายโดยตรง",
        "────────────────────────",
    ])


def _friendly_regime(state: dict, ai_result: dict) -> str:
    from src.customer_narrative import _friendly_regime as _map_regime
    return _map_regime(ai_result.get("market_regime") or (state.get("regime") or {}).get("regime") or "UNKNOWN")


def _friendly_bias(value: object) -> str:
    from src.customer_narrative import _friendly_bias as _map_bias
    return _map_bias(value)


def _format_levels_message(parsed: dict, ai_result: dict) -> str:
    """Render compact resistance / Mean / support map for traders."""
    market_map = ai_result.get("market_map") or {}
    trade = ai_result.get("trade_plan") or {}
    if not market_map:
        market_map = {
            "R1": trade.get("long_tp1"), "R2": trade.get("long_tp2"),
            "R3": trade.get("long_tp3"), "R4": trade.get("long_tp4"),
            "S1": trade.get("short_tp1"), "S2": trade.get("short_tp2"),
            "S3": trade.get("short_tp3"), "S4": trade.get("short_tp4"),
            "pivot": trade.get("gamma_mean"),
        }
    def show(value):
        return _escape(_show(value))
    resistance = [market_map.get(f'R{i}') for i in range(1, 5)]
    support = [market_map.get(f'S{i}') for i in range(1, 5)]
    pivot = market_map.get('pivot', market_map.get('gamma_mean'))
    lines = ["<b>📍 KEY LEVELS</b>", "", "🔴 <b>ต้าน</b>"]
    for i, value in enumerate(resistance, 1):
        lines.append(f"R{i} • {show(value)}")
    lines += ["", f"Mean • {show(pivot)}", "", "🟢 <b>รับ</b>"]
    for i, value in enumerate(support, 1):
        lines.append(f"S{i} • {show(value)}")
    return "\n".join(lines)

def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    """Render all four trade routes with entry reference, SL and TP1-TP5."""
    trade = ai_result.get("trade_plan") or {}
    execution = trade.get("execution_plan") or {}

    # Backward-compatible fallback for snapshots created before four-route mode.
    if execution and not any(key in execution for key in ("long_reclaim", "long_support", "short_rejection", "short_breakdown")):
        # Compatibility bridge for the previous 3-route execution payload.
        execution["long_reclaim"] = execution.get("long") or {}
        execution["long_support"] = execution.get("long_support") or {}
        execution["short_rejection"] = execution.get("short") or {}
        execution["short_breakdown"] = execution.get("short_breakdown") or {}

    if not execution:
        def legacy_payload(prefix: str, side: str, title: str, strategy: str, action: str):
            trigger = trade.get(f"{prefix}_trigger")
            stop = trade.get(f"{prefix}_stop")
            targets = [trade.get(f"{prefix}_tp{i}") for i in range(1, 6)]
            return {
                "route": title,
                "title": title,
                "strategy": strategy,
                "side": side,
                "state": trade.get(f"{prefix}_state") or trade.get("execution_state") or trade.get("status") or "DATA_INSUFFICIENT",
                "trigger": trigger,
                "stop": stop,
                "targets": targets,
                "action": action,
                "risk": {},
            }

        execution = {
            "state": trade.get("execution_state") or trade.get("status") or "DATA_INSUFFICIENT",
            "long_reclaim": legacy_payload("long", "LONG", "BUY — เบรกต้าน", "BREAKOUT_RETEST", "เบรกและยืนเหนือโซน → รีเทสต์ไม่หลุด → BUY"),
            "long_support": legacy_payload("long_support", "LONG_SUPPORT", "BUY — รับด้านล่าง", "REVERSAL", "แตะโซนรับ → reaction → M5 BOS ขึ้น → BUY"),
            "short_rejection": legacy_payload("short", "SHORT", "SELL — ต้านไม่ผ่าน", "REVERSAL / FAILED_RETEST", "เด้งกลับต้าน → rejection → M5 BOS ลง → SELL"),
            "short_breakdown": legacy_payload("short", "SHORT", "SELL — หลุดแนวรับ", "BREAKOUT_RETEST", "หลุดแนวรับ → รีเทสต์ไม่ผ่าน → SELL"),
        }

    def fmt(value):
        return _escape(_show(value))

    def state_text(value: object) -> str:
        state = str(value or "DATA_INSUFFICIENT").upper()
        return {
            "CONFIRMED": "✅ เข้าเงื่อนไข",
            "TRIGGERED": "⏳ เข้าโซนแล้ว • รอยืนยัน",
            "TRIGGERED_WAIT_CONFIRMATION": "⏳ เข้าโซนแล้ว • รอยืนยัน",
            "TRIGGERED_WAIT_RISK_REWARD": "⚠️ เข้าโซน แต่ Risk ไม่ผ่าน",
            "IN_ZONE": "📍 อยู่ในโซน • รอ Action",
            "APPROACHING": "👀 กำลังเข้าโซน",
            "ARMED": "👀 รอจังหวะ",
            "WAIT": "— รอ",
            "NO_TRADE": "🚫 NO TRADE",
            "INVALIDATED": "❌ หลุดเงื่อนไข",
            "DATA_INSUFFICIENT": "⚠️ ข้อมูลไม่พอ",
        }.get(state, state)

    def risk_text(payload: dict) -> str | None:
        risk = payload.get("risk") or {}
        if risk.get("status") == "PASS":
            return None
        reason = str(risk.get("reason") or "").upper()
        if not reason:
            return "🚫 Risk ยังไม่ผ่าน"
        reason_map = {
            "STOP_TOO_FAR": "🚫 SL ไกลเกิน volatility ที่กำหนด",
            "RR_BELOW_MIN": "🚫 TP1 ได้ไม่ถึง 1R",
            "NO_QUALIFIED_TP1": "🚫 ยังไม่มี TP1 ที่คุ้มความเสี่ยง",
            "INVALID_STOP_DIRECTION": "🚫 ตำแหน่ง SL ไม่ถูกด้าน",
            "MISSING_ENTRY_OR_STOP": "🚫 Entry/SL ข้อมูลไม่ครบ",
            "LEVEL_TOO_FAR": "📏 ระดับนี้ไกลจากราคาปัจจุบัน • WAIT",
        }
        return reason_map.get(reason, f"🚫 Risk: {html.escape(reason.lower().replace('_', ' '))}")

    def render_route(payload: dict, title: str, emoji: str, default_action: str) -> list[str]:
        p = payload or {}
        trigger = p.get("trigger")
        stop = p.get("stop")
        targets = list(p.get("targets") or [])
        targets.extend([None] * (5 - len(targets)))
        action = _text(p.get("action")) if p.get("action") else default_action

        lines = [
            f"{emoji} <b>{title}</b>",
            f"ทำแบบนี้: {_escape(action)}",
        ]
        if trigger is not None:
            lines.append(f"เข้าเมื่อ: <b>{fmt(trigger)}</b>")
        else:
            watch = p.get("watch_level")
            ref = "ยังไม่มีโซนใกล้ราคา"
            if watch is not None:
                ref += f" • เฝ้า {fmt(watch)}"
            lines.append(f"เข้าเมื่อ: <b>{ref}</b>")
        lines.append(f"🛑 SL: <b>{fmt(stop)}</b>")
        for i, value in enumerate(targets[:5], 1):
            lines.append(f"🎯 TP{i}: <b>{fmt(value)}</b>")
        lines.append(f"สถานะ: {state_text(p.get('state'))}")
        warning = risk_text(p)
        if warning:
            lines.append(warning)
        return lines

    routes = [
        ("long_reclaim", "🟢", "BUY 1 — เบรกแนวต้าน", "เบรกและยืนเหนือโซน → รีเทสต์ไม่หลุด → BUY"),
        ("long_support", "🟢", "BUY 2 — รับด้านล่าง", "แตะโซนรับ → rejection/absorption → M5 BOS ขึ้น → BUY"),
        ("short_rejection", "🔴", "SELL 1 — ต้านไม่ผ่าน", "เด้งกลับต้าน → rejection → M5 BOS ลง → SELL"),
        ("short_breakdown", "🔴", "SELL 2 — หลุดแนวรับ", "หลุดแนวรับ → รีเทสต์ไม่ผ่าน → M5 BOS ลง → SELL"),
    ]

    bias = str(ai_result.get("bias") or trade.get("direction") or "WAIT").upper()
    preferred_key = execution.get("preferred_setup")
    preferred = execution.get(preferred_key) if preferred_key else None
    if not isinstance(preferred, dict) or preferred.get("state") in {"WAIT", "NO_TRADE", "DATA_INSUFFICIENT", "INVALIDATED"}:
        candidates = [execution.get("short_rejection"), execution.get("short_breakdown")] if bias in {"SELL", "BEARISH"} else [execution.get("long_reclaim"), execution.get("long_support")]
        preferred = next((x for x in candidates if isinstance(x, dict) and x.get("state") not in {"WAIT", "NO_TRADE", "DATA_INSUFFICIENT", "INVALIDATED"}), None)
    pref_title = preferred.get("title") if isinstance(preferred, dict) else None

    lines = [
        "📋 <b>TRADE PLAN</b>",
        "ครบ 4 ทาง • ใช้เฉพาะ Local Zone ใกล้ราคาปัจจุบัน",
        f"มุมมอง: <b>{_escape(bias)}</b>",
        f"แผนเด่น: <b>{_escape(pref_title or 'WAIT')}</b>",
        "แตะระดับ ≠ เข้า • ต้อง Action + Confirmation + Risk ผ่าน",
        "",
    ]

    for i, (key, emoji, title, action) in enumerate(routes):
        if i:
            lines.append("")
        lines.extend(render_route(execution.get(key) or {}, title, emoji, action))

    lines += [
        "",
        "R/S + Mean = Market Map • Entry/SL/TP = Local Trade Setup เท่านั้น",
        "ระบบไม่ส่งคำสั่งซื้อขาย",
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
