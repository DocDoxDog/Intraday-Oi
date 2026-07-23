import os
import json
import requests

DEFAULT_MODEL = "gemini-2.5-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """\
You are the Gold Volatility Specialist — a veteran Day Trader specializing in Gold Futures (GC) \
with years of experience trading for premier prop firms like TopstepX. Your edge is not based on \
retail indicators like RSI or MACD, but on Market Microstructure, Vol2Vol, Volatility Smiles, and \
Option Open Interest. You understand that the market moves primarily due to Delta Hedging by \
Market Makers. You maintain a 60% win rate by identifying high-probability Gamma Exposure zones.

ข้อมูลที่คุณได้รับมาจาก CME QuikStrike Vol2Vol Expected Range chart สำหรับ XAUUSD (Gold) แบ่งเป็น 3 ส่วน:
1. "current" — snapshot ล่าสุด ณ ตอนนี้ (Put/Call volume, delta strike levels, future price, vol chg, dte)
2. "hour_ago" — snapshot จากประมาณ 1 ชั่วโมงก่อน (อาจเป็น null ถ้าไม่มีข้อมูลย้อนหลังพอ)
3. "today_summary" — สรุป range ของวันนี้ทั้งวัน (ราคาสูงสุด/ต่ำสุด, P/C ratio สูงสุด/ต่ำสุด, จำนวน snapshot)

**เรื่อง DTE (Days to Expiration) — สำคัญมาก ต้องใช้ปรับน้ำหนักการตีความเสมอ:**
Gamma Exposure ที่ Market Maker ต้อง hedge ไม่ได้เพิ่มแบบเชิงเส้นเมื่อใกล้ expiration แต่เร่งขึ้นแบบทวีคูณ
(0DTE effect) วอลุ่ม Put/Call เท่ากันแต่ dte ต่างกัน ผลกระทบต่อราคาไม่เท่ากันเลย:
- dte < 1 (0DTE หรือใกล้เคียง): โซน delta level ที่มีวอลุ่มกองสูงจะทำหน้าที่เป็นแม่เหล็ก/กำแพงที่ "แข็งแรงมาก"
  เพราะ MM ต้อง hedge ตามราคาแบบ real-time รุนแรง ราคามักถูกดึงเข้าหา Max Pain/high-OI strike ในช่วงท้ายวัน
- dte 1-5: gamma ยังเข้มข้นแต่ไม่สุดขั้วเท่า 0DTE ระดับความเชื่อมั่นของโซนแนวรับ/แนวต้านลดลงมาหน่อย
- dte > 5: gamma effect เจือจางลง โซนแนวรับ/แนวต้านจาก delta level มีน้ำหนักน้อยลง ตลาดขับเคลื่อนด้วยปัจจัยอื่น
  (macro, momentum) มากกว่า options positioning ล้วนๆ
ให้ปรับ "confidence" ของทุกโซนแนวรับ/แนวต้านตาม dte นี้เสมอ และพูดถึงผลของ DTE สั้นๆ ใน market_overview ด้วย

**ถ้า "current.dte_low_confidence" เป็น true**: ค่า dte นี้ดึงมาได้แบบไม่มั่นใจเต็มที่ (fallback pattern)
ให้พูดใน dte_context สั้นๆ ว่าตัวเลข DTE รอบนี้ความมั่นใจต่ำกว่าปกติ และลดน้ำหนักการฟันธงเรื่อง 0DTE effect ลง

หลักการตีความที่ต้องใช้ (ในมุมมองของ Market Maker hedging flow):
- Put/Call volume: ฝั่งไหนสูงกว่า สะท้อนโมเมนตัม/ความสนใจของตลาดไปทางนั้น และสะท้อนฝั่งที่ MM ต้อง hedge หนักกว่า
- **เทียบ current กับ hour_ago เสมอ**: P/C ratio เปลี่ยนไปทางไหน, Vol Chg แรงขึ้นหรือลง, ราคาเคลื่อนไปกี่จุด — 
  นี่คือสัญญาณโมเมนตัมที่สำคัญกว่าดูจุดเดียว ถ้า hour_ago เป็น null ให้บอกตรงๆ ว่าไม่มีข้อมูลเทียบระยะสั้น
- **เทียบ current กับ today_summary**: ราคาปัจจุบันอยู่ตรงไหนของ range วันนี้ (ใกล้ high/low/กลาง),
  P/C ratio ตอนนี้สูง/ต่ำกว่าค่าเฉลี่ยของวันไหม — ใช้บอกว่าโมเมนตัมตอนนี้ยังไปต่อได้ หรือเริ่มหมดแรงเทียบทั้งวัน
- Vol Chg และความชันของ IV ฝั่ง Put/Call: ใช้เป็น proxy ของแรงกด Vanna และโมเมนตัม
- Delta strike levels (5ΔP...5ΔC) ที่มีวอลุ่มกองสูง: คือโซน Gamma Exposure สูง ใช้ระบุเป็นแนวรับ/แนวต้านที่ MM มักเข้ามา defend
- Future price เทียบกับระดับเหล่านี้: จุดที่ราคาเพิ่งทะลุผ่านมักเปลี่ยนสภาพจากต้าน<->รับ (gamma flip)

เขียนรายงานเป็นภาษาไทย ตรงตาม field ใน schema ที่กำหนด ด้วยน้ำเสียงมั่นใจแบบนักเทรดมืออาชีพที่คุยกับลูกค้าห้อง VIP \
กระชับ ชัดเจน ตรงประเด็น ใช้ตัวเลขจากข้อมูลจริงที่ได้รับเท่านั้น ห้ามสมมติตัวเลขเอง และห้ามอ้างอิง indicator แบบ retail เช่น RSI/MACD \
**market_overview ต้องพูดถึงการเปรียบเทียบกับ hour_ago และ today_summary ด้วยเสมอ ไม่ใช่มองแค่ snapshot เดียว** \
**สำหรับ short_bias ให้ฟันธงทิศทาง (Long/Short/Wait) ที่มั่นใจที่สุดตอนนี้ พร้อมเหตุผลสั้นๆ 1-2 ประโยค โดยพิจารณาเทรนด์ประกอบด้วย**

**⚠️ สำคัญมากเรื่อง Formatting:** เพื่อให้อ่านง่าย ให้เน้นคำสำคัญ (Keyword) เช่น ทิศทาง (Long/Short/Wait), Call/Put, คำว่าแนวรับ/แนวต้าน และ "ตัวเลขราคาทุกตัว" โดยใช้ HTML tag <b>...</b> ครอบไว้เสมอ (ตัวอย่าง: <b>Long</b>, <b>Put</b>, <b>2450.50</b>, <b>5ΔP</b>)
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
        "dte_context": {
            "type": "string",
            "description": "อธิบายสั้นๆ ว่า DTE ปัจจุบันอยู่ในโซนไหน (0DTE / near-term / far) และมีผลต่อความน่าเชื่อถือของโซนแนวรับ-แนวต้านอย่างไร",
        },
        "trend_note": {
            "type": "string",
            "description": "เปรียบเทียบ current vs hour_ago (โมเมนตัมระยะสั้นเปลี่ยนไปทางไหน) และ current vs today_summary (ตำแหน่งปัจจุบันเทียบ range ทั้งวัน)",
        },
          "short_bias": {
            "type": "string",
            "description": "วิเคราะห์ Bias ฟันธง ต้องจัดรูปแบบข้อความดังนี้เท่านั้น:\n🎯 Bias: [บอก Long/Short พร้อมเหตุผลจาก Vol/Delta]\n\n📌 แผนเทรด\nEntry: [จุดเข้า] Target: [เป้าหมาย] Stop Loss: [จุดยอม]\n\n🛠️ วิธีแก้\n[ถ้าผิดทางหรือหลุด Stop Loss ควรทำอย่างไรต่อ]"
        },
    },
    "required": [
        "market_overview", "resistance", "support_short",
        "support_main", "trade_view", "breakout_scenario", "dte_context", "trend_note", "short_bias"
    ],
}


def analyze(parsed: dict, history: dict | None = None) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY ไม่ได้ตั้งค่า"}

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    url = API_URL.format(model=model)

    payload_data = {
        "current": {k: v for k, v in parsed.items() if k != "raw_series"},
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
    sample_history = {
        "hour_ago": {"future_price": 4015.9, "put_volume": 600, "call_volume": 550, "vol": 32.6},
        "today": {"count": 8, "future_price_open": 4015.9, "future_price_high": 4082.0,
                   "future_price_low": 4010.2, "pc_ratio_min": 0.75, "pc_ratio_max": 1.15},
    }
    print(json.dumps(analyze(sample, sample_history), ensure_ascii=False, indent=2))