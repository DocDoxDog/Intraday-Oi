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
    """Render one continuous analyst article; raw evidence stays in the 3 images."""
    narrative = build_customer_narrative(parsed, ai_result)
    article = narrative.get("market_read") or ai_result.get("market_overview") or "ยังไม่มีบทวิเคราะห์ที่ยืนยันได้"

    observed = parsed.get("observed_at") or parsed.get("retrieved_at")
    try:
        dt = datetime.fromisoformat(str(observed).replace("Z", "+00:00")).astimezone(BANGKOK_TZ)
        date_text = f"{dt.day} {dt:%b} {dt.year}"
    except Exception:
        date_text = _thai_datetime_str()

    lines = [
        "<b>GOLD MARKET — " + _escape(date_text) + "</b>",
        f"CFD {_show(parsed.get('cfd_price'))} | FUT. {_show(parsed.get('future_price'))}",
        f"BASIS {_show(parsed.get('basis_diff', parsed.get('basis')))} | IV {_show(parsed.get('vol', parsed.get('iv')))}%",
        f"DTE {_show(parsed.get('dte'))}",
        "",
        _escape(article),
    ]
    return "\n".join(lines)

def _friendly_regime(state: dict, ai_result: dict) -> str:
    from src.customer_narrative import _friendly_regime as _map_regime
    return _map_regime(ai_result.get("market_regime") or (state.get("regime") or {}).get("regime") or "UNKNOWN")


def _friendly_bias(value: object) -> str:
    from src.customer_narrative import _friendly_bias as _map_bias
    return _map_bias(value)


def _format_levels_message(parsed: dict, ai_result: dict) -> str:
    """Show real structural nodes in descending price order."""
    raw=parsed.get("raw_series") or {}
    path=ai_result.get("structural_path") or (raw.get("market_flow") or {}).get("path") or (raw.get("market_state") or {}).get("path") or {}
    nodes=list(path.get("nodes") or (ai_result.get("market_map") or {}).get("structural_nodes") or [])
    current=path.get("current_price") or parsed.get("cfd_price")
    priced=[]
    for n in nodes:
        try:
            level=float(n.get("level",n) if isinstance(n,dict) else n)
        except (TypeError,ValueError):
            continue
        priced.append((level,n))
    priced=sorted({round(level,5):n for level,n in priced}.items(),reverse=True)
    lines=["<b>📍 KEY LEVELS — จุดสำคัญของตลาด</b>"]
    if current is not None: lines.append(f"ราคาปัจจุบัน • <b>{_show(current)}</b>")
    if not priced:
        lines.append("ยังไม่มีจุดสำคัญที่ข้อมูลยืนยันได้")
        return "\n".join(lines)
    for level,n in priced:
        if isinstance(n,dict):
            role=str(n.get("role") or n.get("node_type") or "จุดสำคัญ").replace("_"," ").lower()
        else:
            role="จุดสำคัญ"
        side="เหนือราคา" if current is not None and level>float(current) else "ใต้ราคา"
        lines.append(f"{'↑' if side=='เหนือราคา' else '↓'} <b>{_show(level)}</b> • {role}")
    return "\n".join(lines)

def _format_path_message(parsed: dict, ai_result: dict) -> str:
    """Compact conditional path used when a separate path block is requested."""
    raw=parsed.get("raw_series") or {}
    path=ai_result.get("structural_path") or ((raw.get("market_flow") or {}).get("path")) or ((raw.get("market_state") or {}).get("path")) or {}
    if not isinstance(path,dict) or path.get("status")=="UNKNOWN":
        return ""
    current=path.get("current_price") or parsed.get("cfd_price")
    up=path.get("upper_node") or {}
    down=path.get("lower_node") or {}
    nu=path.get("next_up") or {}
    nd=path.get("next_down") or {}
    lines=["<b>🧭 CONDITIONAL MARKET PATH</b>",f"ตอนนี้ • <b>{_show(current)}</b>"]
    if up.get("level") is not None:
        lines.append(f"ถ้าผ่าน <b>{_show(up['level'])}</b> และยืนได้ → <b>{_show(nu.get('level'))}</b>" if nu.get("level") is not None else f"ถ้าผ่าน <b>{_show(up['level'])}</b> → รอดู node ถัดไป")
        lines.append(f"ถ้าไม่ผ่าน → กลับเข้าโซนเดิม")
    if down.get("level") is not None:
        lines.append(f"ถ้าหลุด <b>{_show(down['level'])}</b> และยืนต่ำกว่า → <b>{_show(nd.get('level'))}</b>" if nd.get("level") is not None else f"ถ้าหลุด <b>{_show(down['level'])}</b> → รอดู node ถัดไป")
        lines.append(f"ถ้าหลุดแล้ว reclaim → กลับเข้าโซนเดิม")
    return "\n".join(lines)

def _format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    """Render every deterministic risk-valid plan; no confirmation instructions."""
    trade = ai_result.get("trade_plan") or {}
    plans = trade.get("research_plans") or []

    if not plans:
        return "<b>🎯 TRADE PLAN</b>\\nตอนนี้ยังไม่มีแผนที่มี Entry / SL / TP ครบและผ่าน Risk Gate"

    lines = ["<b>🎯 TRADE PLAN</b>"]
    for plan in plans:
        side = "🟢 BUY" if str(plan.get("side")).upper() == "BUY" else "🔴 SELL"
        route = _escape(str(plan.get("route") or "SETUP").replace("_", " "))
        lines += [
            "",
            f"<b>{side} — {route}</b>",
            f"Entry {_show(plan.get('entry'))}",
            f"SL {_show(plan.get('stop_loss'))}",
        ]
        for i, target in enumerate(plan.get("targets") or [], 1):
            lines.append(f"TP{i} {_show(target)}")

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

        # Telegram surface: 3 evidence images -> 1 article -> 1 trade-plan message.
        for message in (
            _format_analysis_message(parsed, ai_result),
            _format_trade_plan_message(parsed, ai_result),
        ):
            for chunk in _chunk(message):
                _post_with_retry(
                    TELEGRAM_API.format(token=token),
                    {"chat_id": cid, "text": chunk, "parse_mode": "HTML"},
                )
                time.sleep(0.25)

        print(f"✅ Telegram analyst bundle sent to {cid}")
