"""Telegram delivery and presentation for the GOLD Market Analyst."""

from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from src.customer_narrative import build_customer_narrative
from src.market_state import desk_note_schedule


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


def _clean_article_text(value: object) -> str:
    """Remove raw telemetry/data-dump fragments from the customer article."""
    text = str(value or "").strip()
    if not text:
        return ""
    kept: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if re.match(r"^(?:1H|2H|TODAY|YESTERDAY)\s*:", paragraph, flags=re.IGNORECASE):
            continue
        if re.match(r"^(?:OI|GEX|IV|TECHNICAL|MACRO|NEWS)\s*:", paragraph, flags=re.IGNORECASE):
            continue
        kept.append(paragraph)
    unique: list[str] = []
    seen: set[str] = set()
    for paragraph in kept:
        key = re.sub(r"\s+", " ", paragraph).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(paragraph)
    return "\n\n".join(unique)


def _single_line(value: object) -> str:
    """Flatten analyst prose into one Desk Note line without raw telemetry."""  # [run-live] verify placeholder filter
    text = _clean_article_text(value)
    text = re.sub(r"(?:^|\n)(?:NOW|CHANGE|CAUSE|CONFLICT|ACTION)\s*[:\-]?", " ", text, flags=re.IGNORECASE)
    # Customer-facing copy must never expose unresolved telemetry placeholders.
    text = re.sub(r"\bUNKNOWN\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bN/?A\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*บริเวณ\s*(?=แล้ว|และ|แต่|ก่อน|หลัง|$)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _note_levels(parsed: dict, ai_result: dict) -> tuple[list[float], list[float]]:
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    market_map = ai_result.get("market_map") or {}
    level_sources = [
        market_map.get("R1"), market_map.get("R2"),
        market_map.get("S1"), market_map.get("S2"),
        (state.get("levels") or {}).get("resistance_current"),
        (state.get("levels") or {}).get("support_current"),
        (state.get("levels") or {}).get("resistance_main"),
        (state.get("levels") or {}).get("support_main"),
        (state.get("levels") or {}).get("gamma_wall_up_next"),
        (state.get("levels") or {}).get("gamma_wall_down_next"),
        *((state.get("levels") or {}).get("gamma_wall_up_chain") or [])[:3],
        *((state.get("levels") or {}).get("gamma_wall_down_chain") or [])[:3],
    ]
    resist = []
    support = []
    current = parsed.get("cfd_price")
    try:
        current_f = float(current) if current is not None else None
    except (TypeError, ValueError):
        current_f = None
    for value in level_sources:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if current_f is None or number > current_f:
            if number not in resist:
                resist.append(number)
        elif number < current_f:
            if number not in support:
                support.append(number)
    return sorted(resist)[:2], sorted(support, reverse=True)[:2]


def _format_analysis_message(parsed: dict, ai_result: dict) -> str:
    """Render the canonical customer narrative with deterministic execution context."""  # [run-live] full contract verification
    observed = parsed.get("observed_at") or parsed.get("retrieved_at")
    schedule = ai_result.get("desk_note_context") or desk_note_schedule(observed)
    slot = str(schedule.get("slot") or "-")
    valid_until = str(ai_result.get("valid_until_label") or schedule.get("valid_until_label") or "-")

    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    gamma = state.get("gamma") or {}
    liquidity = state.get("liquidity") or {}
    decision = state.get("decision") or {}
    levels = state.get("levels") or {}

    def n(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def s(v, d=2):
        x = n(v)
        return f"{x:,.{d}f}" if x is not None else "-"

    cfd = n(parsed.get("cfd_price"))
    fut = n(parsed.get("future_price"))
    basis = n(parsed.get("basis_diff"))
    iv = n(parsed.get("vol"))
    dte = n(parsed.get("dte"))

    put_wall = n(gamma.get("put_wall")) or n(levels.get("support_current"))
    call_wall = n(gamma.get("call_wall")) or n(levels.get("resistance_current"))

    structural = str(
        decision.get("structural_bias")
        or ai_result.get("structural_bias")
        or ai_result.get("bias")
        or "MIXED"
    ).upper()
    b = "BEARISH" if structural in {"SELL", "BEARISH"} else "BULLISH" if structural in {"BUY", "BULLISH"} else "MIXED"

    narrative = build_customer_narrative(parsed, ai_result)
    story = str(narrative.get("market_read") or "").strip()
    if not story:
        story = _single_line(
            ai_result.get("market_overview")
            or ai_result.get("liquidity_story")
            or ai_result.get("what")
            or ""
        )
    if not story:
        story = f"ราคาปัจจุบันอยู่แถว {s(cfd)} และยังรอการตอบสนองที่ระดับสำคัญ"

    # Comparative change is deterministic and compact; raw history labels never reach Telegram.
    hist = ai_result.get("reference_selection") or (state.get("history") or {}).get("reference_selection") or {}
    sel = hist.get("selected") or {}
    ch = sel.get("change") or {}
    dp = n(ch.get("future_price"))
    dg = n(ch.get("gex_net"))
    if dp is not None and abs(dp) > 0.0001:
        change = f"CHANGE: Futures {'เพิ่มขึ้น' if dp > 0 else 'ลดลง'} {s(abs(dp))} เทียบกับ{sel.get('label') or 'รอบก่อนหน้า'}"
        if dg is not None and abs(dg) > 0.0001:
            change += f" | Net Gamma {'ดีขึ้น' if dg > 0 else 'แย่ลง'}"
    elif sel.get("meaningful_change") is False:
        change = "CHANGE: โครงสร้างยังไม่เปลี่ยนอย่างมีนัยสำคัญ"
    else:
        change = "CHANGE: ยังไม่มีการเปลี่ยนโครงสร้างที่มากพอให้เปลี่ยน thesis"

    gate = str(liquidity.get("gate") or "").upper()
    preferred = str(liquidity.get("preferred_event") or "").upper()
    sweep = gate == "SWEEP_DETECTED"

    if preferred in {"BUY_SIDE_SWEEP", "BUY_SIDE_LIQUIDITY"}:
        event = "Buy-side Sweep"
    elif preferred in {"SELL_SIDE_SWEEP", "SELL_SIDE_LIQUIDITY"}:
        event = "Sell-side Sweep"
    else:
        event = "Buy-side Sweep" if b == "BEARISH" else "Sell-side Sweep" if b == "BULLISH" else "Liquidity Sweep"

    in_range = (
        cfd is not None
        and put_wall is not None
        and call_wall is not None
        and put_wall < cfd < call_wall
    )
    next_up = n(levels.get("gamma_wall_up_next"))
    next_down = n(levels.get("gamma_wall_down_next"))

    if in_range:
        if b == "BEARISH":
            action = (
                f"ACTION: PENDING — รอ {event} เหนือ {s(call_wall)} แล้ว Reclaim "
                f"ก่อน Short → {s(put_wall)}"
            )
        elif b == "BULLISH":
            action = (
                f"ACTION: PENDING — รอ {event} ใต้ {s(put_wall)} แล้ว Reclaim "
                f"ก่อน Long → {s(call_wall)}"
            )
        else:
            action = "ACTION: PENDING — รอ Sweep + Reaction หรือ Break + Acceptance ก่อนเลือกฝั่ง"
    elif cfd is not None and call_wall is not None and cfd >= call_wall:
        target = s(next_up) if next_up is not None else "Gamma Wall ถัดไป"
        action = f"ACTION: Break + Acceptance เหนือ {s(call_wall)} → continuation ไป {target}"
    elif cfd is not None and put_wall is not None and cfd <= put_wall:
        target = s(next_down) if next_down is not None else "Gamma Wall ถัดไป"
        action = f"ACTION: Break + Acceptance ใต้ {s(put_wall)} → continuation ไป {target}"
    else:
        action = "ACTION: PENDING — ยังไม่มี structural event ที่พอให้ไล่ราคา"

    lines = [
        f"<b>GOLD MARKET — {slot}</b>",
        _escape(f"CFD {s(cfd)} | FUT. {s(fut)} | BASIS {s(basis)} | IV {s(iv)}%"),
        _escape(f"DTE. {s(dte)}"),
    ]
    for paragraph in story.splitlines():
        paragraph = paragraph.strip()
        if paragraph:
            lines.append(_escape(paragraph))

    # Explicit liquidity events are evidence, not prose guesses.
    if sweep:
        lines.append(_escape(f"Liquidity: เกิด {event} แล้ว"))

    context = _single_line(ai_result.get("why") or "")
    if context and context not in story:
        lines.append(_escape(f"CONTEXT: {context}"))

    lines.append(_escape(change))
    lines.append(_escape(action))
    lines.append(_escape(f"Valid Until: {valid_until}"))
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
    """Render the primary trade route only when the deterministic execution gate passes."""
    execution = ((ai_result.get("trade_plan") or {}).get("execution_plan") or {})
    primary = execution.get("primary_setup")

    if not isinstance(primary, dict):
        # Legacy payloads may expose only route arrays. Keep the customer contract
        # conservative: without an explicit execution gate, never publish fills.
        bias = str(ai_result.get("structural_bias") or ai_result.get("bias") or "").upper()
        preferred = "SHORT" if bias == "BEARISH" else "LONG" if bias == "BULLISH" else ""
        candidates = [x for x in (execution.get("routes") or []) if isinstance(x, dict)]
        primary = next(
            (x for x in candidates if str(x.get("side") or "").upper().startswith(preferred)),
            candidates[0] if candidates else None,
        )

    if not isinstance(primary, dict):
        return "<b>🎯 TRADE PLAN</b>\nPENDING — ยังไม่มี Primary setup ที่ยืนยันได้"

    side = str(primary.get("side") or "").upper()
    title = "BUY" if side.startswith("LONG") else "SELL" if side.startswith("SHORT") else side
    emoji = "🟢" if title == "BUY" else "🔴" if title == "SELL" else "⚪"

    state_name = str(primary.get("state") or "").upper()
    permission = str(execution.get("trade_permission") or "").upper()
    execution_ready = bool(primary.get("execution_ready")) and permission == "ENTER_CONDITION_SATISFIED"

    schedule = ai_result.get("desk_note_context") or desk_note_schedule(
        parsed.get("observed_at") or parsed.get("retrieved_at")
    )
    valid_until = str(ai_result.get("valid_until_label") or schedule.get("valid_until_label") or "-")

    if not execution_ready:
        event = (
            primary.get("preferred_liquidity_event")
            or primary.get("event_required")
            or primary.get("action")
            or "รอ event ที่โซน"
        )
        state_label = {
            "PENDING_LIQUIDITY_SWEEP": "PENDING — รอ Liquidity Sweep",
            "WAIT_LIQUIDITY_SWEEP": "PENDING — รอ Liquidity Sweep",
            "TRIGGERED_WAIT_CONFIRMATION": "PENDING — รอ Price Confirmation",
            "TRIGGERED_WAIT_RISK_REWARD": "PENDING — รอ Risk Gate",
            "ARMED": "PENDING — ยังไม่ผ่าน Execution Gate",
            "APPROACHING": "PENDING — ราคาเข้าใกล้โซน",
            "IN_ZONE": "PENDING — อยู่ในโซน แต่ยังไม่ยืนยัน",
            "NO_TRADE": "NO TRADE",
        }.get(state_name, "PENDING")
        trigger = primary.get("trigger") or primary.get("entry_reference")
        lines = [
            "<b>🎯 TRADE PLAN</b>",
            f"{emoji} <b>{title or 'WAIT'}</b> — {_escape(primary.get('strategy') or primary.get('route') or 'PRIMARY SETUP')}",
            f"State <b>{_escape(state_label)}</b>",
            f"Event <b>{_escape(event)}</b>",
        ]
        if trigger is not None:
            lines.append(f"Trigger Zone <b>{_escape(_show(trigger))}</b>")
        lines.append("Entry / SL / TP ยังไม่แสดงจนกว่า Execution Gate จะผ่าน")
        lines.append(f"Valid Until <b>{_escape(valid_until)}</b>")
        return "\n".join(lines)

    entry = primary.get("trigger")
    if entry is None:
        entry = primary.get("entry_reference")
    if entry is None:
        entry = primary.get("entry")
    stop = primary.get("stop")
    targets = [x for x in (primary.get("targets") or []) if x is not None][:5]
    if entry is None or stop is None or not targets:
        return "<b>🎯 TRADE PLAN</b>\nNO TRADE — source-derived Entry/SL/TP ไม่ครบ"

    rr_values = [x for x in (primary.get("rr") or []) if x is not None]
    if rr_values:
        rr_text = _show(rr_values[0])
    else:
        try:
            entry_f, stop_f, tp_f = float(entry), float(stop), float(targets[0])
            risk = (entry_f - stop_f) if title == "BUY" else (stop_f - entry_f)
            reward = (tp_f - entry_f) if title == "BUY" else (entry_f - tp_f)
            rr_text = f"{reward / risk:.2f}" if risk > 0 and reward > 0 else "-"
        except (TypeError, ValueError, ZeroDivisionError):
            rr_text = "-"

    lines = [
        "<b>🎯 TRADE PLAN</b>",
        f"{emoji} <b>{title}</b> — {_escape(primary.get('strategy') or primary.get('route') or 'PRIMARY SETUP')}",
        "State <b>EXECUTABLE</b>",
        f"Entry <b>{_escape(_show(entry))}</b>",
        f"SL <b>{_escape(_show(stop))}</b>",
    ]
    for i, tp in enumerate(targets, 1):
        lines.append(f"TP{i} <b>{_escape(_show(tp))}</b>")
    lines.append(f"R:R <b>{_escape(rr_text)}</b>")
    action_raw = primary.get("action") or primary.get("trigger")
    if action_raw not in (None, ""):
        lines.append(f"Trigger <b>{_escape(action_raw)}</b>")
    invalid_raw = primary.get("cancel_if") or primary.get("invalidation")
    if invalid_raw not in (None, ""):
        lines.append(f"Invalid <b>{_escape(invalid_raw)}</b>")
    lines.append(f"Valid Until <b>{_escape(valid_until)}</b>")
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


def _prepare_telegram_photo(image_bytes: bytes) -> tuple[bytes, str, str]:
    """Normalize rendered images to Telegram-safe dimensions/encoding."""
    try:
        from io import BytesIO
        from PIL import Image

        source = Image.open(BytesIO(image_bytes))
        source.load()
        source.thumbnail((3500, 3500), Image.Resampling.LANCZOS)
        if source.mode != "RGB":
            source = source.convert("RGB")
        output = BytesIO()
        source.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue(), "image.jpg", "image/jpeg"
    except Exception:
        return image_bytes, "image.png", "image/png"


def _send_photo_with_fallback(token: str, chat_id: str, photo_url: str, caption: str, image_bytes: bytes | None = None) -> None:
    """Prefer direct multipart delivery so Telegram does not fetch private Supabase URLs."""
    url = TELEGRAM_PHOTO_API.format(token=token)
    if image_bytes:
        upload_bytes, filename, content_type = _prepare_telegram_photo(image_bytes)
        upload = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": (filename, upload_bytes, content_type)},
            timeout=30,
        )
        if upload.status_code < 400:
            return
        raise RuntimeError(
            f"Telegram direct photo upload failed HTTP {upload.status_code}: {(upload.text or '')[:500]}"
        )
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
        upload_bytes, filename, content_type = _prepare_telegram_photo(image.content)
        upload = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": (filename, upload_bytes, content_type)},
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
    screenshot_bytes: bytes | None = None,
    gamma_table_bytes: bytes | None = None,
    gamma_table_full_bytes: bytes | None = None,
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
        # A bad/oversized evidence image must never suppress the text bundle.
        photo_jobs = [
            (gamma_table_bytes, gamma_table_url, "GOLD GAMMA TABLE — Multi-Expiration"),
            (gamma_table_full_bytes, gamma_table_full_url, "GOLD GAMMA TABLE — FULL DATA"),
            (screenshot_bytes, screenshot_url, "QUIKSTRIKE OI — Source Screenshot"),
        ]
        for image_bytes, image_url, caption in photo_jobs:
            if not (image_bytes or image_url):
                continue
            try:
                _send_photo_with_fallback(
                    token, cid, image_url or "", caption, image_bytes=image_bytes
                )
            except Exception as exc:
                print(f"⚠️ Telegram photo skipped ({caption}): {exc}", flush=True)


        # Telegram is intentionally compact: three evidence images, one article, one plan.
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
