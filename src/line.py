"""
line.py
=======
ส่งรายงานเข้า LINE Official Account แบบ Broadcast
(ส่งหาทุกคนที่แอดเพื่อนกับ OA — ไม่ต้องมี userId รายคน, ใช้แค่ Channel Access Token)

หมายเหตุ:
- Broadcast API ของ LINE ฟรี 500 ข้อความ/เดือน (บน Free plan) แล้วเริ่มคิดเงินตาม
  แพ็กเกจ Messaging API — เช็คโควตาใน LINE Official Account Manager ก่อนใช้งานจริง
- ต้องสร้าง LINE Official Account + Messaging API channel ใน LINE Developers Console
  แล้วเอา "Channel access token (long-lived)" มาใส่ใน LINE_CHANNEL_ACCESS_TOKEN
"""

import os
import time
import requests

LINE_BROADCAST_API = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# LINE จำกัดสูงสุด 5 message objects ต่อ 1 คำขอ broadcast
MAX_MESSAGES_PER_REQUEST = 5


def _text_message(text: str) -> dict:
    # LINE จำกัดความยาวข้อความ text ที่ 5000 ตัวอักษร/ก้อน
    return {"type": "text", "text": text[:5000]}


def _image_message(url: str) -> dict:
    return {
        "type": "image",
        "originalContentUrl": url,
        "previewImageUrl": url,
    }


def format_message(parsed: dict, ai_result: dict) -> str:
    """Backward-compatible alias for message 3."""
    dte = parsed.get("dte")
    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    return (
        f"GOLD MARKET ANALYST V2 • วันที่ {__import__('datetime').datetime.now().day} "
        f"{__import__('datetime').datetime.now().strftime('%b')} "
        f"| เวลา {__import__('datetime').datetime.now().strftime('%H:%M')} น.\n"
        f"Futures {parsed.get('future_price','-')} | CFD {parsed.get('cfd_price','-')} | DTE {dte if dte is not None else '-'}\n"
        f"Status: {str(ai_result.get('analysis_status') or 'CONFIRMED').upper()} | "
        f"Bias: {str(ai_result.get('bias') or ai_result.get('short_bias') or 'WAIT').upper()}\n\n"
        f"WHAT\n{ai_result.get('what') or ai_result.get('market_overview') or '-'}\n\n"
        f"WHY\n{ai_result.get('why') or '-'}\n\n"
        f"POSITIONING\n{ai_result.get('positioning') or '-'}"
    )


def _levels_message(parsed: dict, ai_result: dict) -> str:
    raw = parsed.get("raw_series") or {}
    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    levels = ai_result.get("levels") or {}
    scenarios = ai_result.get("scenarios") or {}
    show=lambda v: "-" if v is None or v == "" else str(v)
    return (
        "KEY LEVELS\n"
        f"ต้านไกล: {show(levels.get('resistance_far'))}\n"
        f"ต้านหลัก: {show(levels.get('resistance_main'))}\n"
        f"ต้านใกล้: {show(levels.get('resistance_current'))}\n"
        f"รับใกล้: {show(levels.get('support_current'))}\n"
        f"รับหลัก: {show(levels.get('support_main'))}\n"
        f"รับลึก: {show(levels.get('support_deep'))}\n\n"
        f"GAMMA TERM STRUCTURE\n"
        f"{len(gamma.get('columns') or [])} expirations | +GEX zone {show(zones.get('highest_positive_gamma'))} | -GEX zone {show(zones.get('highest_negative_gamma'))}\n\n"
        f"SCENARIOS\n"
        f"🟢 Bull — {scenarios.get('bull') or '-'}\n"
        f"🔴 Bear — {scenarios.get('bear') or '-'}\n"
        f"🟡 Sideway — {scenarios.get('sideway') or '-'}"
    )


def _trade_plan_message(parsed: dict, ai_result: dict) -> str:
    trade = ai_result.get("trade_plan") or {}
    return (
        "TRADE PLAN\n"
        f"Status: {str(trade.get('status') or 'NO_TRADE').upper()}\n"
        f"{trade.get('setup') or '-'}\n"
        f"Confirmation: {trade.get('confirmation') or '-'}\n"
        f"Invalidation: {trade.get('invalidation') or '-'}\n"
        f"Risk: {trade.get('risk_note') or '-'}"
    )


def _post_broadcast(token: str, messages: list[dict]) -> None:
    resp = requests.post(
        LINE_BROADCAST_API,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"messages": messages},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LINE broadcast ล้มเหลว [{resp.status_code}]: {resp.text}")


def _post_push(token: str, to: str, messages: list[dict]) -> None:
    resp = requests.post(
        LINE_PUSH_API,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"to": to, "messages": messages},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LINE group push ล้มเหลว [{resp.status_code}]: {resp.text}")


def send(parsed: dict, ai_result: dict, screenshot_url: str | None = None, gamma_table_url: str | None = None) -> None:
    """Send exactly five LINE messages: Gamma, source, analyst, levels/scenarios, trade plan."""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN ไม่ได้ตั้งค่า — เช็ค GitHub Secrets หรือไฟล์ .env")

    messages: list[dict] = []
    if gamma_table_url:
        messages.append(_image_message(gamma_table_url))
    if screenshot_url:
        messages.append(_image_message(screenshot_url))
    messages.extend([
        _text_message(format_message(parsed, ai_result)),
        _text_message(_levels_message(parsed, ai_result)),
        _text_message(_trade_plan_message(parsed, ai_result)),
    ])

    errors: list[str] = []
    for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
        chunk = messages[i:i + MAX_MESSAGES_PER_REQUEST]
        try:
            _post_broadcast(token, chunk)
            print(f"✅ ส่ง LINE broadcast สำเร็จ ({len(chunk)} ข้อความ)")
        except Exception as e:
            print(f"❌ ส่ง LINE broadcast ล้มเหลว: {e}")
            errors.append(str(e))
        time.sleep(0.5)

    group_id = os.environ.get("LINE_GROUP_ID", "").strip()
    if group_id:
        for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
            chunk = messages[i:i + MAX_MESSAGES_PER_REQUEST]
            try:
                _post_push(token, group_id, chunk)
                print(f"✅ ส่ง LINE group push สำเร็จ ({len(chunk)} ข้อความ)")
            except Exception as e:
                print(f"❌ ส่ง LINE group push ล้มเหลว: {e}")
                errors.append(str(e))
            time.sleep(0.5)
    else:
        print("⏭️  ข้าม LINE group push (ไม่ได้ตั้งค่า LINE_GROUP_ID)")

    if errors:
        raise RuntimeError(f"LINE broadcast ล้มเหลว {len(errors)} chunk(s): " + " | ".join(errors))
