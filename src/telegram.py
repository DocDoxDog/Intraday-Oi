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
import time
from datetime import datetime, timezone, timedelta
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_API = "https://api.telegram.org/bot{token}/sendPhoto"

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
    dte = parsed.get("dte")
    dte_line = f" (DTE: {dte})" if dte is not None else ""

    if "error" in ai_result:
        return f"{header}\n\n⚠️ AI analysis error: {ai_result['error']}"

    return (
        f"📊 <b>รายงาน Volatility & Options Flow (Gold)</b>{dte_line}\n"
        f"{header}\n\n"
        f"<b>• ภาพรวมตลาด</b>\n{ai_result.get('market_overview', '-')}\n\n"
        f"<b>• บริบท DTE</b>\n{ai_result.get('dte_context', '-')}\n\n"
        f"<b>• เทรนด์เทียบย้อนหลัง</b>\n{ai_result.get('trend_note', '-')}\n\n"
        f"<b>• โซนสำคัญ</b>\n"
        f"แนวต้านหลัก: {ai_result.get('resistance', '-')}\n"
        f"แนวรับระยะสั้น: {ai_result.get('support_short', '-')}\n"
        f"แนวรับหลัก: {ai_result.get('support_main', '-')}\n\n"
        f"<b>• มุมมองการเทรดระยะสั้น</b>\n{ai_result.get('trade_view', '-')}\n\n"
        f"<b>• กรณีทะลุกรอบ</b>\n{ai_result.get('breakout_scenario', '-')}"
    )


def send(
    parsed: dict,
    ai_result: dict,
    screenshot_url: str | None = None,
    chat_ids: list[str] | None = None,
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ไม่ได้ตั้งค่า — เช็ค GitHub Secrets หรือไฟล์ .env")

    # ถ้าไม่ได้ส่ง chat_ids เข้ามาตรงๆ (เช่น จาก Supabase customers table)
    # fallback ไปอ่าน TELEGRAM_CHAT_ID จาก env แบบเดิม เพื่อไม่ให้ของเดิมพัง
    if chat_ids is None:
        chat_ids_env = os.environ.get("TELEGRAM_CHAT_ID")
        if not chat_ids_env:
            raise RuntimeError(
                "ไม่มี chat_ids ให้ส่ง — ทั้ง customers table (Supabase) และ "
                "TELEGRAM_CHAT_ID (env) ว่างเปล่าทั้งคู่"
            )
        chat_ids = [cid.strip() for cid in chat_ids_env.split(',') if cid.strip()]

    if not chat_ids:
        print("⚠️  ไม่มี chat_id ให้ส่ง (ข้ามขั้นตอนนี้)")
        return

    # ข้อความที่ 2: วิเคราะห์ละเอียด
    detailed_text = format_message(parsed, ai_result)
    
    # ข้อความที่ 3: วิเคราะห์สั้น Bias ที่มั่นใจที่สุด
    bias_text = ai_result.get('short_bias', 'ไม่มีข้อมูล Bias')
    short_bias_message = f"🎯 <b>Short Bias ฟันธง!</b>\n{bias_text}"

    # วนลูปยิง 3 ข้อความหาแต่ละคน
    for cid in chat_ids:
        
        # 1️⃣ ข้อความแรก: ส่งรูปภาพ (ถ้ามี)
        if screenshot_url:
            try:
                requests.post(
                    TELEGRAM_PHOTO_API.format(token=token),
                    json={"chat_id": cid, "photo": screenshot_url},
                    timeout=20,
                )
            except Exception as e:
                print(f"⚠️ ส่งรูปไปยัง ID: {cid} ล้มเหลว: {e}")
        time.sleep(0.5)

        # 2️⃣ ข้อความที่สอง: วิเคราะห์ละเอียด (รองรับ <b>)
        try:
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": detailed_text, "parse_mode": "HTML"},
                timeout=15,
            )
        except Exception as e:
            print(f"❌ ส่งวิเคราะห์ละเอียด ไปยัง ID: {cid} ล้มเหลว: {e}")
        time.sleep(0.5)
            
        # 3️⃣ ข้อความที่สาม: Short Bias สั้นๆ กระแทกใจ (รองรับ <b>)
        try:
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": short_bias_message, "parse_mode": "HTML"},
                timeout=15,
            )
            print(f"✅ ส่งข้อมูลครบ 3 แชท ไปยัง ID: {cid} สำเร็จ")
        except Exception as e:
            print(f"❌ ส่ง Short Bias ไปยัง ID: {cid} ล้มเหลว: {e}")
            
        # หน่วงเวลา 1 วินาทีเต็มๆ ก่อนวนไปส่งหาคนถัดไป
        time.sleep(1)
        
