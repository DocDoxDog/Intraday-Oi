"""
analyze.py
==========
ส่งข้อมูลที่ parse แล้วเข้า Claude API ให้สรุปเป็น sentiment/insight
บังคับ output เป็น JSON structure เพื่อ parse ต่อง่าย
"""

import os
import json
import anthropic

SYSTEM_PROMPT = """\
คุณเป็นนักวิเคราะห์ options flow สำหรับ XAUUSD (Gold) โดยใช้ข้อมูลจาก CME QuikStrike \
Vol2Vol Expected Range chart

หลักการตีความที่ต้องใช้:
- IV Smile/Skew shape: put skew ชันกว่า call = ตลาดกลัวขาลงมากกว่าขาขึ้น
- Put/Call volume ratio: >1 = bearish lean, <1 = bullish lean, ~1 = neutral
- Vol Chg: ใช้เป็น proxy ของแรงกด Vanna (บวกมาก = dealer อาจต้อง hedge เพิ่มตามทิศทางราคา)
- Future price เทียบกับ delta levels (5ΔP...5ΔC): ใกล้ extreme = ตลาดเคลื่อนไหวแรง, ใกล้ ATM = neutral

ตอบเป็น JSON เท่านั้น ไม่มี markdown fence ไม่มีข้อความอื่นนอกเหนือจาก JSON object นี้:
{
  "sentiment": "bullish | bearish | neutral",
  "confidence": "low | medium | high",
  "key_levels": ["..."],
  "vanna_pressure": "...",
  "risk_note": "..."
}
"""


def analyze(parsed: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": json.dumps(parsed, ensure_ascii=False)}
        ],
    )

    text = message.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # เผื่อ model ตอบไม่ตรง format เป๊ะ — เก็บ raw text ไว้ debug แทนที่จะพัง pipeline
        return {"error": "ไม่สามารถ parse JSON จาก Claude ได้", "raw": text}
