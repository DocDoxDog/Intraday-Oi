"""
telegram.py
===========
ประกอบผลวิเคราะห์เป็นรายงานสไตล์นักวิเคราะห์ (ตาม template ที่กำหนด) แล้วส่งเข้า Telegram
ผ่าน Bot API ตรงๆ (ใช้ requests ไม่ต้องพึ่ง library เพิ่ม)

ต้องมี:
- TELEGRAM_BOT_TOKEN  -> จาก BotFather
- TELEGRAM_CHAT_ID    -> chat/channel/group id ที่จะส่งเข้า (รองรับหลาย ID คั่นด้วยลูกน้ำ)
"""

import os
import time  # <--- เพิ่ม time สำหรับหน่วงเวลา
from datetime import datetime, timezone, timedelta
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

BANGKOK_TZ = timezone(timedelta(hours=7))


def _thai_datetime_str(dt: datetime | None = None) -> str:
    dt = (dt or datetime.now(timezone.utc)).astimezone(BANGKOK_TZ)
    buddhist_year = dt.year + 543
    return f"วันที่ {dt.day} {THAI_MONTHS[dt.month]} {buddhist_year} | เวลา {dt.strftime('%H:%M')} น."


def format_message(parsed: dict, ai_result: dict) -> str:
    header = _thai_datetime_str()

    if "error" in ai_result:
        return f"{header}\n\n⚠️ AI analysis error: {ai_result['error']}"

    return (
        f"{header}\n\n"
        f"• ภาพรวมตลาด\n{ai_result.get('market_overview', '-')}\n\n"
        f"• โซนสำคัญ\n"
        f"แนวต้านหลัก: {ai_result.get('resistance', '-')}\n"
        f"แนวรับระยะสั้น: {ai_result.get('support_short', '-')}\n"
        f"แนวรับหลัก: {ai_result.get('support_main', '-')}\n\n"
        f"• มุมมองการเทรดระยะสั้น\n{ai_result.get('trade_view', '-')}\n\n"
        f"• กรณีทะลุกรอบ\n{ai_result.get('breakout_scenario', '-')}"
    )


def send(parsed: dict, ai_result: dict) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_ids_env = os.environ.get("TELEGRAM_CHAT_ID")  # <--- รับค่า String ที่มีลูกน้ำ
    
    if not token or not chat_ids_env:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN หรือ TELEGRAM_CHAT_ID ไม่ได้ตั้งค่า — "
            "เช็ค GitHub Secrets หรือไฟล์ .env"
        )

    text = format_message(parsed, ai_result)
    
    # หั่น Chat ID ด้วยลูกน้ำและลบช่องว่างทิ้ง
    chat_ids = [cid.strip() for cid in chat_ids_env.split(',') if cid.strip()]
    
    # วนลูปส่งข้อความหาทุกคน
    for cid in chat_ids:
        try:
            resp = requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": text},
                timeout=15,
            )
            resp.raise_for_status()
            print(f"✅ ส่ง Telegram ไปยัง ID: {cid} สำเร็จ")
        except Exception as e:
            print(f"❌ ส่ง Telegram ไปยัง ID: {cid} ล้มเหลว: {e}")
            
        # หน่วงเวลา 0.5 วินาที ป้องกัน Telegram แบนบอทข้อหาสแปม
        time.sleep(0.5)

    resp.raise_for_status()
