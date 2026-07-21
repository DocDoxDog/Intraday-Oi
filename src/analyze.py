"""
analyze.py
==========
ส่งข้อมูลที่ parse แล้วเข้า Gemini API ให้สรุปเป็น sentiment/insight
ใช้ REST API ตรงๆ ผ่าน requests (ไม่ต้องลง SDK เพิ่ม)
บังคับ output เป็น JSON ด้วย responseSchema ของ Gemini (แม่นกว่าสั่งด้วย prompt เฉยๆ)

Docs: https://ai.google.dev/api/generate-content
"""

import os
import json
import requests

# ปรับ model ได้ผ่าน env var GEMINI_MODEL โดยไม่ต้องแก้โค้ด
# ถ้า model นี้ถูก deprecate ในอนาคต เปลี่ยนที่ .env ได้เลย
DEFAULT_MODEL = "gemini-2.5-flash"

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """\
คุณเป็นนักวิเคราะห์ options flow สำหรับ XAUUSD (Gold) โดยใช้ข้อมูลจาก CME QuikStrike \
Vol2Vol Expected Range chart

หลักการตีความที่ต้องใช้:
- IV Smile/Skew shape: put skew ชันกว่า call = ตลาดกลัวขาลงมากกว่าขาขึ้น
- Put/Call volume ratio: >1 = bearish lean, <1 = bullish lean, ~1 = neutral
- Vol Chg: ใช้เป็น proxy ของแรงกด Vanna (บวกมาก = dealer อาจต้อง hedge เพิ่มตามทิศทางราคา)
- Future price เทียบกับ delta levels (5ΔP...5ΔC): ใกล้ extreme = ตลาดเคลื่อนไหวแรง, ใกล้ ATM = neutral

วิเคราะห์ข้อมูล JSON ที่ผู้ใช้ส่งมา แล้วตอบตาม schema ที่กำหนด
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "key_levels": {"type": "array", "items": {"type": "string"}},
        "vanna_pressure": {"type": "string"},
        "risk_note": {"type": "string"},
    },
    "required": ["sentiment", "confidence", "key_levels", "vanna_pressure", "risk_note"],
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
        # เก็บ response body ไว้ debug ด้วย เพราะ Gemini มักบอกสาเหตุ error ชัดใน body
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
        "contract": "G3TN6", "future_price": 4067, "future_chg": 12.3,
        "put_volume": 819, "call_volume": 870, "vol": 33.1, "vol_chg": 0.5,
        "delta_levels": {"5ΔP": 3980, "5ΔC": 4150},
    }
    print(json.dumps(analyze(sample), ensure_ascii=False, indent=2))
