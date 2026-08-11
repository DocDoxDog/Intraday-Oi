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
    dte = parsed.get("dte")
    dte_line = ""
    if dte is not None:
        if str(dte).startswith("0."):
            dte_line = f" (INTRADAY | DTE: {dte})"
        else:
            dte_line = f" (DTE: {dte})"

    if "error" in ai_result:
        return f"⚠️ AI analysis error: {ai_result['error']}"

    return (
        f"📊 รายงาน Volatility & Options Flow (Gold){dte_line}\n\n"
        f"• ภาพรวมตลาด\n{ai_result.get('market_overview', '-')}\n\n"
        f"• โซนสำคัญ\n"
        f" - แนวต้านไกล: {ai_result.get('resistance_far', '-')}\n"
        f" - แนวต้านหลัก: {ai_result.get('resistance_main', '-')}\n"
        f" - แนวต้านปัจจุบัน: {ai_result.get('resistance_current', '-')}\n"
        f" - แนวรับปัจจุบัน: {ai_result.get('support_current', '-')}\n"
        f" - แนวรับหลัก: {ai_result.get('support_main', '-')}\n"
        f" - แนวรับลึก: {ai_result.get('support_deep', '-')}\n\n"
        f"• Scenario\n"
        f"1) Bull Case\n{ai_result.get('bull_case', '-')}\n\n"
        f"2) Bear Case\n{ai_result.get('bear_case', '-')}\n\n"
        f"3) Sideway Case (มุมมองหลัก)\n{ai_result.get('sideway_case', '-')}"
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


def send(parsed: dict, ai_result: dict, screenshot_url: str | None = None) -> None:
    """
    ส่ง broadcast ไปหาผู้ที่แอดเพื่อน LINE OA ทุกคน
    ไม่ต้องรู้ userId รายคน — LINE จัดการกระจายให้เองตาม Channel access token
    """
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN ไม่ได้ตั้งค่า — เช็ค GitHub Secrets หรือไฟล์ .env")

    detailed_text = format_message(parsed, ai_result)
    bias_text = ai_result.get("short_bias", "ไม่มีข้อมูล Bias")
    short_bias_message = f"🎯 Bias ฟันธง!\n{bias_text}"

    messages: list[dict] = []
    if screenshot_url:
        messages.append(_image_message(screenshot_url))
    messages.append(_text_message(detailed_text))
    messages.append(_text_message(short_bias_message))

    # แบ่งเป็น chunk ละไม่เกิน 5 message objects ตามข้อจำกัดของ LINE API
    for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
        chunk = messages[i : i + MAX_MESSAGES_PER_REQUEST]
        try:
            _post_broadcast(token, chunk)
            print(f"✅ ส่ง LINE broadcast สำเร็จ ({len(chunk)} ข้อความ)")
        except Exception as e:
            print(f"❌ ส่ง LINE broadcast ล้มเหลว: {e}")
        time.sleep(0.5)
