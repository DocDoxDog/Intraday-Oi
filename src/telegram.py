"""
telegram.py
===========
ประกอบผลวิเคราะห์เป็นรายงานสไตล์นักวิเคราะห์ แล้วส่งเข้า Telegram
รูปแบบอัปเดต: รองรับ CFD Note, โซนสำคัญครบถ้วน (ต้านไกล/หลัก/ปัจจุบัน, รับปัจจุบัน/หลัก/ลึก),
และ Scenarios (1) Bull Case, 2) Bear Case, 3) Sideway Case) พร้อม Chat 2 (Bias & Action Plan)
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
    
    dte_line = ""
    if dte is not None:
        if str(dte).startswith("0."):
            dte_line = f" (INTRADAY | DTE: {dte})"
        else:
            dte_line = f" (DTE: {dte})"

    if "error" in ai_result:
        return f"{header}\n\n⚠️ AI analysis error: {ai_result['error']}"

    cfd_note = ai_result.get('cfd_note', '(อ้างอิงราคา CFD ปรับลด 25 จุด)')

    return (
        f"📊 <b>รายงาน Volatility & Options Flow (Gold)</b>{dte_line}\n"
        f"{header}\n"
        f"<i>{cfd_note}</i>\n\n"
        f"<b>• ภาพรวมตลาด</b>\n{ai_result.get('market_overview', '-')}\n\n"
        f"<b>• โซนสำคัญ</b>\n"
        f" • แนวต้านไกล: {ai_result.get('resistance_far', '-')}\n"
        f" • แนวต้านหลัก: {ai_result.get('resistance_main', '-')}\n"
        f" • แนวต้านปัจจุบัน: {ai_result.get('resistance_current', '-')}\n"
        f" • แนวรับปัจจุบัน: {ai_result.get('support_current', '-')}\n"
        f" • แนวรับหลัก: {ai_result.get('support_main', '-')}\n"
        f" • แนวรับลึก: {ai_result.get('support_deep', '-')}\n\n"
        f"<b>• Scenario</b>\n"
        f"<b>1) Bull Case</b>\n{ai_result.get('bull_case', '-')}\n\n"
        f"<b>2) Bear Case</b>\n{ai_result.get('bear_case', '-')}\n\n"
        f"<b>3) Sideway Case (มุมมองหลัก)</b>\n{ai_result.get('sideway_case', '-')}"
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

    if chat_ids is None:
        chat_ids_env = os.environ.get("TELEGRAM_CHAT_ID")
        if not chat_ids_env:
            raise RuntimeError("ไม่มี chat_ids ให้ส่ง")
        chat_ids = [cid.strip() for cid in chat_ids_env.split(',') if cid.strip()]

    if not chat_ids:
        print("⚠️  ไม่มี chat_id ให้ส่ง (ข้ามขั้นตอนนี้)")
        return

    detailed_text = format_message(parsed, ai_result)
    bias_text = ai_result.get('short_bias', 'ไม่มีข้อมูล Bias')
    short_bias_message = f"🎯 <b>Bias ฟันธง!</b>\n{bias_text}"

    for cid in chat_ids:
        # 1. ส่งรูปภาพ (ถ้ามี)
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

        # 2. ส่งรายงานละเอียด (Chat 1)
        try:
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": detailed_text, "parse_mode": "HTML"},
                timeout=15,
            )
        except Exception as e:
            print(f"❌ ส่งวิเคราะห์ละเอียด ไปยัง ID: {cid} ล้มเหลว: {e}")
        time.sleep(0.5)
            
        # 3. ส่ง Bias ฟันธง (Chat 2)
        try:
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": short_bias_message, "parse_mode": "HTML"},
                timeout=15,
            )
            print(f"✅ ส่งข้อมูลครบ 3 แชท ไปยัง ID: {cid} สำเร็จ")
        except Exception as e:
            print(f"❌ ส่ง Short Bias ไปยัง ID: {cid} ล้มเหลว: {e}")
            
        time.sleep(1)
