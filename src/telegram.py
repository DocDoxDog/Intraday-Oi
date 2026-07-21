"""
telegram.py
===========
ส่งผลวิเคราะห์เข้า Telegram ผ่าน Bot API ตรงๆ (ไม่ต้องพึ่ง library เพิ่ม ใช้ requests)

ต้องมี:
- TELEGRAM_BOT_TOKEN  -> จาก BotFather
- TELEGRAM_CHAT_ID    -> chat/channel/group id ที่จะส่งเข้า (ใช้ id เดียวกับ QontWise bot เดิมได้
                         ถ้าจะแยก tier ค่อยขยายเป็น list ทีหลัง)
"""

import os
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def format_message(parsed: dict, ai_result: dict) -> str:
    contract = parsed.get("contract") or "N/A"
    future_price = parsed.get("future_price")
    future_chg = parsed.get("future_chg")
    put_v = parsed.get("put_volume")
    call_v = parsed.get("call_volume")
    vol = parsed.get("vol")
    vol_chg = parsed.get("vol_chg")

    pc_ratio = None
    if put_v and call_v:
        pc_ratio = round(put_v / call_v, 2)

    if "error" in ai_result:
        ai_block = f"⚠️ AI analysis error: {ai_result['error']}"
    else:
        levels = ", ".join(ai_result.get("key_levels", [])) or "-"
        ai_block = (
            f"Sentiment: <b>{ai_result.get('sentiment', '-').upper()}</b> "
            f"(confidence: {ai_result.get('confidence', '-')})\n"
            f"Vanna pressure: {ai_result.get('vanna_pressure', '-')}\n"
            f"Key levels: {levels}\n"
            f"Risk note: {ai_result.get('risk_note', '-')}"
        )

    future_line = f"Future: {future_price} ({future_chg:+g})" if future_chg is not None else f"Future: {future_price}"

    return (
        f"📊 <b>OI Intraday — {contract}</b>\n\n"
        f"{future_line}\n"
        f"Put/Call: {put_v}/{call_v} (ratio {pc_ratio})\n"
        f"Vol: {vol}  Vol Chg: {vol_chg}\n\n"
        f"{ai_block}"
    )


def send(parsed: dict, ai_result: dict) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN หรือ TELEGRAM_CHAT_ID ไม่ได้ตั้งค่า — "
            "เช็ค GitHub Secrets หรือไฟล์ .env"
        )

    text = format_message(parsed, ai_result)
    resp = requests.post(
        TELEGRAM_API.format(token=token),
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    resp.raise_for_status()
