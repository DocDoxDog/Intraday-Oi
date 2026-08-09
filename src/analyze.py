"""
analyze.py
==========
ส่งข้อมูลที่ parse แล้วเข้า Gemini API ให้สรุปเป็นรายงานสไตล์นักวิเคราะห์ (ภาษาไทย)
รูปแบบอัปเดต: รองรับ CFD Price Calibration, ภาพรวมตลาดเชิงลึก, โซนสำคัญ (แนวต้านไกล-ใกล้ / แนวรับใกล้-ไกล),
และ Scenario แยกชัดเจน (Bull Case, Bear Case, Sideway Case) พร้อม Bias และแผนเทรด
"""

import os
import json
import requests

DEFAULT_MODEL = "gemini-3.5-flash-lite"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """\
You are the Gold Volatility Specialist — a veteran Day Trader specializing in Gold Futures (GC) and CFD. \
Your edge is based on Market Microstructure, Vol2Vol, Volatility Smile/Skew, Option Open Interest, and Dealer Hedging Flows (Gamma, Vanna, Charm).

ข้อมูลที่คุณได้รับมาจาก CME QuikStrike Vol2Vol Expected Range chart ประกอบด้วย:
1. "current" — snapshot ล่าสุด (Put/Call volume, delta strike levels, future price, vol chg, dte)
2. "hour_ago" — snapshot จาก 1 ชั่วโมงก่อน
3. "today_summary" — สรุป range ทั้งวัน
4. "raw_series_summary" — สรุปการกระจายตัวของ Gamma ตาม strike, Volatility Settle shape, และ Expected Ranges

**คำสั่งพิเศษสำหรับการแสดงผลราคา (CFD Calibration):**
- เนื่องจากกราฟ QuikStrike อ้างอิงราคา Futures (GC) ให้คำนวณและระบุราคา CFD โดยการปรับลดลง 25 จุด (หรือตาม offset ที่เหมาะสม) ควบคู่ไปกับราคา Futures เสมอ เพื่อให้ลูกค้าที่เทรด CFD นำไปใช้งานได้ทันที

**โครงสร้างการวิเคราะห์และรายงานผล (บังคับตาม Schema):**
1. **cfd_note**: หมายเหตุการอ้างอิงราคา (เช่น อ้างอิงราคา CFD ปรับลด 25 จุด)
2. **market_overview**: วิเคราะห์ภาพรวมตลาด เปรียบเทียบ Put vs Call volume, การเคลื่อนไหวของราคา Futures/CFD, และระดับ IV ว่าสะท้อนความผันผวนระดับใด
3. **resistance_far**, **resistance_main**, **resistance_current**: แนวต้านไกล, หลัก, และปัจจุบัน (พร้อมอ้างอิงระดับ strike)
4. **support_current**, **support_main**, **support_deep**: แนวรับปัจจุบัน, หลัก, และลึก (พร้อมอ้างอิงระดับ strike)
5. **bull_case**, **bear_case**, **sideway_case**: แยก 3 กรณีชัดเจน (Bull Case, Bear Case, Sideway Case)
6. **short_bias**: ฟันธง Bias (Long/Short/Wait), แผนเทรด (Entry, Target, Stop Loss), และวิธีแก้ทาง

เขียนรายงานเป็นภาษาไทย มืออาชีพ กระชับ ห้ามสมมติตัวเลขเอง ใช้ข้อมูลจริงเท่านั้น
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "cfd_note": {
            "type": "string",
            "description": "หมายเหตุการเทียบราคา เช่น (อ้างอิงราคา CFD ปรับลด 25 จุด)",
        },
        "market_overview": {
            "type": "string",
            "description": "ภาพรวมตลาด: สรุป Call/Put volume, ราคาปัจจุบัน Futures/CFD, และสภาวะ IV",
        },
        "resistance_far": {"type": "string", "description": "แนวต้านไกล พร้อมรายละเอียด strike"},
        "resistance_main": {"type": "string", "description": "แนวต้านหลัก พร้อมรายละเอียด strike"},
        "resistance_current": {"type": "string", "description": "แนวต้านปัจจุบัน พร้อมรายละเอียด strike"},
        "support_current": {"type": "string", "description": "แนวรับปัจจุบัน พร้อมรายละเอียด strike"},
        "support_main": {"type": "string", "description": "แนวรับหลัก พร้อมรายละเอียด strike"},
        "support_deep": {"type": "string", "description": "แนวรับลึก พร้อมรายละเอียด strike"},
        "bull_case": {"type": "string", "description": "1) Bull Case: เงื่อนไขทะลุแนวต้านและผลกระทบ Gamma Squeeze"},
        "bear_case": {"type": "string", "description": "2) Bear Case: เงื่อนไขหลุดแนวรับและแรงกดดันเทขาย"},
        "sideway_case": {"type": "string", "description": "3) Sideway Case: มุมมองหลักเมื่อ IV สูงและการแกว่งตัว"},
        "short_bias": {
            "type": "string",
            "description": "🎯 Bias ฟันธง & แผนเทรด จัดรูปแบบ:\n🎯 Bias: [Long/Short/Wait พร้อมเหตุผล]\n\n📌 แผนเทรด\nEntry: [...] Target: [...] Stop Loss: [...]\n\n🛠️ วิธีแก้\n[แนวทางจัดการเมื่อผิดทาง]"
        },
    },
    "required": [
        "cfd_note", "market_overview", "resistance_far", "resistance_main", "resistance_current",
        "support_current", "support_main", "support_deep", "bull_case", "bear_case", "sideway_case", "short_bias"
    ],
}


def summarize_raw_series(raw_series) -> dict:
    if not raw_series or not isinstance(raw_series, list):
        return {"note": "No raw series available"}
    
    summary = {}
    try:
        put_data, call_data, vol_data, ranges_data = [], [], [], []
        for series in raw_series:
            name = series.get("name", "")
            data = series.get("data", [])
            if name == "Put": put_data = data
            elif name == "Call": call_data = data
            elif name == "Vol Settle": vol_data = data
            elif name == "Ranges": ranges_data = data
        
        combined_strikes = {}
        for p in put_data:
            combined_strikes[p.get("x")] = combined_strikes.get(p.get("x"), 0) + p.get("y", 0)
        for c in call_data:
            combined_strikes[c.get("x")] = combined_strikes.get(c.get("x"), 0) + c.get("y", 0)
            
        sorted_strikes = sorted(combined_strikes.items(), key=lambda item: item[1], reverse=True)
        summary["top_volume_strikes"] = [{"strike": s[0], "total_vol": s[1]} for s in sorted_strikes[:5]]
        summary["vol_settle_sample"] = [{"strike": v.get("x"), "iv": v.get("y")} for v in vol_data[::max(1, len(vol_data)//5)]]
        summary["ranges_detected"] = [r.get("x") for r in ranges_data if r.get("x") is not None]
    except Exception as e:
        summary["error_parsing_raw"] = str(e)
    return summary


def analyze(parsed: dict, history: dict | None = None) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY ไม่ได้ตั้งค่า"}

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    url = API_URL.format(model=model)

    raw_series = parsed.get("raw_series")
    raw_summary = summarize_raw_series(raw_series)

    payload_data = {
        "current": {k: v for k, v in parsed.items() if k != "raw_series"},
        "raw_series_summary": raw_summary,
        "hour_ago": (history or {}).get("hour_ago"),
        "today_summary": (history or {}).get("today"),
    }

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": json.dumps(payload_data, ensure_ascii=False, default=str)}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=45,
            )
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                continue
            return {"error": f"Gemini API error: {e}"}

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:
        return {"error": f"Failed to parse response: {e}"}
