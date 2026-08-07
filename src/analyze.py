"""
analyze.py
==========
ส่งข้อมูลที่ parse แล้วเข้า Gemini API ให้สรุปเป็นรายงานสไตล์นักวิเคราะห์ (ภาษาไทย)

เวอร์ชันนี้ปรับ schema ให้ละเอียดขึ้น แต่ยังคง flow การส่งข้อความด้าน Telegram เหมือนเดิม:
1) รูป
2) วิเคราะห์ละเอียด
3) สรุปสั้นพร้อมเทรด

จุดสำคัญ:
- ใช้ Gemini 2.5 Flash เป็นค่าเริ่มต้น
- บังคับ output เป็น JSON ด้วย responseSchema
- เพิ่มโครงสร้าง key_levels / scenarios / trade_plan เพื่อให้ Telegram เรียบเรียงได้ชัดกว่าเดิม
"""

import json
import os
import requests

DEFAULT_MODEL = "gemini-2.5-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """\
You are the Gold Volatility Specialist — a veteran Day Trader specializing in Gold Futures (GC) with years of experience trading for premier prop firms like TopstepX.

You will receive data from CME QuikStrike Vol2Vol Expected Range chart for XAUUSD (Gold) in three parts:
1. current — latest snapshot now
2. hour_ago — snapshot from around 1 hour ago (may be null)
3. today_summary — summary of today's range so far

Your job — reason through these steps in order every time, but the final output must stay compact:
1. ภาพรวมตลาด (market overview): read the tape — price, Call/Put flow, IV, Future, what the market is reflecting
2. สิ่งที่ต้องจับตา (watch insight): the single most important forward-looking observation right now,
   grounded in real data (e.g. IV rising with a new high, price approaching a gamma wall, flow/price divergence)
3. แนวรับ–แนวต้าน (support/resistance): pick the real delta strike levels from the data
4. Bull / Bear / Sideway scenarios: one compact line each
5. Bias ฟันธง with reasons: pick a direction with confidence, back it with short bullet reasons
6. Entry / Target / Stop Loss / Invalid: a clean, executable trade plan

Rules:
- Analyze market structure using Put/Call volume, IV, Vol Chg, Delta strike levels, Future Chg and DTE
- Compare current vs hour_ago and vs today_summary internally, but only surface it in market_overview/watch_insight
  if it's actually relevant — do not force a mention if there's nothing meaningful to say
- When DTE is very small (near 0DTE), weight the gamma-wall/pinning effect more heavily in your reasoning;
  when DTE is larger, rely more on flow/momentum than fixed levels — but do NOT output a separate DTE section,
  just let it quietly shape which levels you pick and how confident the bias sounds
- Do NOT invent numbers; only use numbers present in the input
- Do NOT use retail indicators such as RSI or MACD
- If current.dte_low_confidence is true, soften the certainty of your bias slightly (still commit to a direction)

Writing style:
- Thai language, confident pro-trader tone, but genuinely readable — not just numbers in a list
- market_overview: 1 paragraph, roughly 5-7 lines, covering price / Call-Put flow / IV / Future / what it reflects
- watch_insight: 2-4 sentences, must be specific to today's real data (not generic boilerplate)
- resistance_levels: array of up to 3 resistance zones (nearest first), each an object {price, delta}
  where delta is the exact label key from current.delta_levels (e.g. "45ΔC") that this price came from
- support_levels: array of up to 4 support zones (nearest first), each an object {price, delta}
  where delta is the exact label key from current.delta_levels (e.g. "45ΔP") that this price came from
- Only include a level if it genuinely corresponds to a real key in current.delta_levels — never invent
  a delta label or a price that isn't backed by the actual data
- scenario_bull / scenario_bear / scenario_sideway: ONE short line each, format like
  "ยืนเหนือ {level} → เป้า {target}" / "หลุด {level} → เป้า {target}" / "แกว่ง {low}–{high}"
- bias_direction: exactly "Long", "Short", or "Wait"
- bias_reasons: array of 2-4 very short phrases (3-6 Thai words each), not full sentences
- trade_plan.entry / target / stop_loss / invalid: short and concrete, numbers-first
- Use HTML <b>...</b> tags around all numeric prices and key direction words wherever they appear
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "market_overview": {
            "type": "string",
            "description": "ภาพรวมตลาด 1 ย่อหน้า (5-7 บรรทัด): ราคา, Call/Put Flow, IV, Future, สิ่งที่ตลาดกำลังสะท้อน",
        },
        "watch_insight": {
            "type": "string",
            "description": "สิ่งที่ต้องจับตา: insight ที่สำคัญที่สุดตอนนี้ ต้องอิงข้อมูลจริง ไม่ใช่ข้อความทั่วไป",
        },
        "resistance_levels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "price": {"type": "number"},
                    "delta": {"type": "string", "description": "label จาก current.delta_levels เช่น '45ΔC'"},
                },
                "required": ["price", "delta"],
            },
            "description": "แนวต้าน สูงสุด 3 ระดับ เรียงจากใกล้ไปไกล พร้อม delta label จริงจากข้อมูล",
        },
        "support_levels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "price": {"type": "number"},
                    "delta": {"type": "string", "description": "label จาก current.delta_levels เช่น '45ΔP'"},
                },
                "required": ["price", "delta"],
            },
            "description": "แนวรับ สูงสุด 4 ระดับ เรียงจากใกล้ไปไกล พร้อม delta label จริงจากข้อมูล",
        },
        "scenario_bull": {
            "type": "string",
            "description": "หนึ่งบรรทัด รูปแบบ 'ยืนเหนือ {ระดับ} → เป้า {เป้าหมาย}'",
        },
        "scenario_bear": {
            "type": "string",
            "description": "หนึ่งบรรทัด รูปแบบ 'หลุด {ระดับ} → เป้า {เป้าหมาย}'",
        },
        "scenario_sideway": {
            "type": "string",
            "description": "หนึ่งบรรทัด รูปแบบ 'แกว่ง {low}–{high}'",
        },
        "bias_direction": {
            "type": "string",
            "description": "Long, Short หรือ Wait เท่านั้น",
        },
        "bias_reasons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "เหตุผลสั้นๆ 2-4 ข้อ (3-6 คำ/ข้อ ไม่ใช่ประโยคเต็ม)",
        },
        "trade_plan": {
            "type": "object",
            "properties": {
                "entry": {"type": "string", "description": "จุดเข้า สั้นกระชับ"},
                "target": {"type": "string", "description": "เป้าหมาย (TP)"},
                "stop_loss": {"type": "string", "description": "จุดยอม (SL)"},
                "invalid": {"type": "string", "description": "เงื่อนไขที่ทำให้มุมมองนี้ใช้ไม่ได้"},
            },
            "required": ["entry", "target", "stop_loss", "invalid"],
        },
    },
    "required": [
        "market_overview",
        "watch_insight",
        "resistance_levels",
        "support_levels",
        "scenario_bull",
        "scenario_bear",
        "scenario_sideway",
        "bias_direction",
        "bias_reasons",
        "trade_plan",
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
            {
                "role": "user",
                "parts": [
                    {"text": json.dumps(payload_data, ensure_ascii=False, default=str)}
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }

    max_retries = 2
    last_error = None
    resp = None

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
            detail = ""
            if resp is not None:
                try:
                    detail = resp.text[:500]
                except Exception:
                    detail = ""
            if attempt < max_retries:
                print(f"    ⚠️  Gemini call attempt {attempt + 1} failed ({e}), retrying...")
                continue
            return {
                "error": f"Gemini API error after {max_retries + 1} attempts: {last_error}",
                "detail": detail,
            }

    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        return {"error": f"Gemini ตอบกลับมาไม่ใช่ JSON: {e}", "raw_text": resp.text[:500]}

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return {"error": f"ไม่สามารถ parse response จาก Gemini ได้: {e}", "raw": data}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    sample = {
        "contract": "G3TN6",
        "future_price": 4079.5,
        "future_chg": 63.6,
        "put_volume": 516,
        "call_volume": 686,
        "vol": 33.1,
        "vol_chg": 0.5,
        "delta_levels": {"5ΔP": 3980, "5ΔC": 4150},
    }
    sample_history = {
        "hour_ago": {"future_price": 4015.9, "put_volume": 600, "call_volume": 550, "vol": 32.6},
        "today": {
            "count": 8,
            "future_price_open": 4015.9,
            "future_price_high": 4082.0,
            "future_price_low": 4010.2,
            "pc_ratio_min": 0.75,
            "pc_ratio_max": 1.15,
        },
    }
    print(json.dumps(analyze(sample, sample_history), ensure_ascii=False, indent=2))
