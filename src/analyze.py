"""
analyze.py
==========
ส่งข้อมูลที่ parse แล้วเข้า Gemini API ให้สรุปเป็นรายงานสไตล์นักวิเคราะห์ (ภาษาไทย)
รูปแบบตาม template ที่กำหนด: ภาพรวมตลาด / โซนสำคัญ / มุมมองเทรดระยะสั้น / กรณีทะลุกรอบ

ปรับปรุงใหม่: เพิ่มทฤษฎี Market Microstructure (Gamma Flip, Vanna, Charm, 0DTE Dynamics) 
และจัดระเบียบ Schema ให้แสดงผลใน Telegram ได้อย่างสะอาดตา อ่านง่าย เป็นระเบียบ
"""

import os
import json
import requests

DEFAULT_MODEL = "gemini-3.5-flash-lite"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """\
You are the Gold Volatility Specialist — a veteran Day Trader specializing in Gold Futures (GC) \
with years of experience trading for premier prop firms. Your edge is based on Market Microstructure, \
Vol2Vol, Volatility Smile/Skew, Option Open Interest, and Dealer Hedging Flows (Gamma, Vanna, Charm).

ข้อมูลที่คุณได้รับมาจาก CME QuikStrike Vol2Vol Expected Range chart ประกอบด้วย:
1. "current" — snapshot ล่าสุด (Put/Call volume, delta strike levels, future price, vol chg, dte)
2. "hour_ago" — snapshot จาก 1 ชั่วโมงก่อน
3. "today_summary" — สรุป range ทั้งวัน
4. "raw_series_summary" — สรุปการกระจายตัวของ Gamma ตาม strike, Volatility Settle shape, และ Expected Ranges

**หลักการวิเคราะห์เชิงลึก (Advanced Market Microstructure):**
- **0DTE & Gamma Exposure**: เมื่อ DTE น้อยกว่า 1 วัน แรงกดดันจากการ Hedge ของ Market Maker จะสูงทวีคูณ โซนที่มีวอลุ่มหนาแน่นจะทำหน้าที่เป็นแม่เหล็ก (Pinning) หรือกำแพงป้องกันที่แข็งแกร่ง
- **Vanna & Charm Effect**: พิจารณาว่าความเปลี่ยนแปลงของ Implied Volatility (Vanna) และการเสื่อมของเวลา (Charm) ส่งผลให้ Dealer ต้องซื้อหรือขาย Futures เพิ่มเติมอย่างไร
- **Gamma Flip & Range**: ระบุจุดเปลี่ยนผ่านของสภาพคล่อง และประเมินว่าราคาปัจจุบันอยู่ในกรอบ Expected Move หรือกำลังจะ Breakout

เขียนรายงานเป็นภาษาไทย จัดรูปแบบให้สะอาดตา อ่านง่าย เป็นระเบียบ ตรงตาม field ใน schema ที่กำหนด \
ใช้ตัวเลขจากข้อมูลจริงเท่านั้น ห้ามสมมติตัวเลข และห้ามอ้างอิง indicator ทั่วไปเช่น RSI/MACD \
**สำหรับ short_bias ให้ฟันธงทิศทางชัดเจนตามรูปแบบที่กำหนด**
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "market_overview": {
            "type": "string",
            "description": "📊 ภาพรวมตลาด: สรุปทิศทาง Put vs Call volume, ราคาปัจจุบัน, โมเมนตัม และแรงกดดันจาก Dealer Hedging",
        },
        "resistance": {
            "type": "string",
            "description": "🔴 แนวต้านหลัก: ระบุระดับราคาและเหตุผลเชิง Gamma/Strike",
        },
        "support_short": {
            "type": "string",
            "description": "🟡 แนวรับระยะสั้น: ระบุระดับราคาและเหตุผลสนับสนุน",
        },
        "support_main": {
            "type": "string",
            "description": "🟢 แนวรับหลัก / แนวรับลึก: ระบุโซนป้องกันสำคัญ",
        },
        "trade_view": {
            "type": "string",
            "description": "💡 มุมมองการเทรดระยะสั้น: จุดสังเกตการณ์และจังหวะเข้าทำกำไร",
        },
        "breakout_scenario": {
            "type": "string",
            "description": "⚡ กรณีทะลุกรอบ: ผลกระทบหากราคา Breakout หรือหลุดแนวรับสำคัญ",
        },
        "dte_context": {
            "type": "string",
            "description": "⏳ DTE & Volatility Context: ผลกระทบของอายุสัญญาและ Vanna/Charm ต่อความแข็งแกร่งของโซน",
        },
        "trend_note": {
            "type": "string",
            "description": "📈 Trend & Momentum Note: เปรียบเทียบกับ 1 ชั่วโมงก่อนและช่วงเช้าของวัน",
        },
        "short_bias": {
            "type": "string",
            "description": "🎯 Bias & Action Plan (จัดรูปแบบตามนี้):\n🎯 Bias: [Long/Short/Wait พร้อมเหตุผล]\n\n📌 แผนเทรด\nEntry: [...] Target: [...] Stop Loss: [...]\n\n🛠️ วิธีแก้\n[แนวทางจัดการเมื่อผิดทาง]"
        },
    },
    "required": [
        "market_overview", "resistance", "support_short",
        "support_main", "trade_view", "breakout_scenario", "dte_context", "trend_note", "short_bias"
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
    last_error = None
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
            last_error = e
            if attempt < max_retries:
                continue
            return {"error": f"Gemini API error: {last_error}"}

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:
        return {"error": f"Failed to parse response: {e}"}
