"""
analyze.py
==========
ส่งข้อมูลที่ parse แล้วเข้า Gemini API ให้สรุปเป็นรายงานสไตล์นักวิเคราะห์ (ภาษาไทย)
รูปแบบตาม template ที่กำหนด: ภาพรวมตลาด / โซนสำคัญ / มุมมองเทรดระยะสั้น / กรณีทะลุกรอบ

ใช้ REST API ตรงๆ ผ่าน requests (ไม่ต้องลง SDK เพิ่ม)
บังคับ output เป็น JSON ด้วย responseSchema ของ Gemini แล้วค่อยประกอบเป็นข้อความใน telegram.py

Docs: https://ai.google.dev/api/generate-content
"""

import os
import json
import requests

DEFAULT_MODEL = "gemini-2.5-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """\
คุณเป็นนักวิเคราะห์ options flow สำหรับ XAUUSD (Gold) โดยใช้ข้อมูลจาก CME QuikStrike \
Vol2Vol Expected Range chart (Put/Call volume, delta strike levels, future price, vol chg)

หลักการตีความที่ต้องใช้:
- Put/Call volume: ฝั่งไหนสูงกว่า สะท้อนโมเมนตัม/ความสนใจของตลาดไปทางนั้น
- Vol Chg และความชันของ IV ฝั่ง Put/Call: ใช้เป็น proxy ของแรงกด Vanna และโมเมนตัม
- Delta strike levels (5ΔP...5ΔC) ที่มีวอลุ่มกองสูง: ใช้ระบุเป็นแนวรับ/แนวต้าน
- Future price เทียบกับระดับเหล่านี้: จุดที่ราคาเพิ่งทะลุผ่านมักเปลี่ยนสภาพจากต้าน<->รับ

เขียนรายงานเป็นภาษาไทย ตรงตาม field ใน schema ที่กำหนด โทนเหมือนนักวิเคราะห์มืออาชีพ \
กระชับ ชัดเจน ใช้ตัวเลขจากข้อมูลจริงที่ได้รับเท่านั้น ห้ามสมมติตัวเลขเอง
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "market_overview": {
            "type": "string",
            "description": "ภาพรวมตลาด: เทียบ Put vs Call volume, ราคาปัจจุบันและการเปลี่ยนแปลง, โมเมนตัมที่สะท้อนจาก IV/Vol Chg",
        },
        "resistance": {"type": "string", "description": "แนวต้านหลัก พร้อมเหตุผล"},
        "support_short": {"type": "string", "description": "แนวรับระยะสั้น พร้อมเหตุผล"},
        "support_main": {"type": "string", "description": "แนวรับหลัก/แนวรับลึก พร้อมเหตุผล"},
        "trade_view": {
            "type": "string",
            "description": "มุมมองการเทรดระยะสั้น: ราคาปัจจุบันเทียบกับโซนสำคัญ, จังหวะเข้าที่แนะนำ",
        },
        "breakout_scenario": {
            "type": "string",
            "description": "กรณีทะลุกรอบ: ถ้าประคองตัวได้จะเกิดอะไร, ถ้าหลุดแนวจะเกิดอะไร",
        },
    },
    "required": [
        "market_overview", "resistance", "support_short",
        "support_main", "trade_view", "breakout_scenario",
    ],
}


def analyze(parsed: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY ไม่ได้ตั้งค่า"}

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    url = API_URL.format(model=model)

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": json.dumps(parsed, ensure_ascii=False)}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }

    try:
        resp = requests.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        detail = ""
        try:
            detail = resp.text[:500]
        except Exception:
            pass
        return {"error": f"Gemini API error: {e}", "detail": detail}

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return {"error": f"ไม่สามารถ parse response จาก Gemini ได้: {e}", "raw": data}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sample = {
        "contract": "G3TN6", "future_price": 4079.5, "future_chg": 63.6,
        "put_volume": 516, "call_volume": 686, "vol": 33.1, "vol_chg": 0.5,
        "delta_levels": {"5ΔP": 3980, "5ΔC": 4150},
    }
    print(json.dumps(analyze(sample), ensure_ascii=False, indent=2))
