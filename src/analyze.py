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

Your job:
- Analyze market structure using Put/Call volume, IV, Vol Chg, Delta strike levels, Future Chg and DTE
- Compare current vs hour_ago whenever available
- Compare current vs today_summary whenever available
- Produce concise but high-signal Thai analysis
- Keep the output strictly aligned with the JSON schema
- Do NOT invent numbers; only use numbers present in the input
- Do NOT use retail indicators such as RSI or MACD
- When DTE is very small, strengthen the explanation of gamma effect; when DTE is larger, reduce confidence on level-based interpretation
- If current.dte_low_confidence is true, mention that DTE confidence is lower than usual and reduce emphasis on 0DTE interpretation

Writing style:
- Confident, concise, pro trader tone
- Use HTML <b>...</b> tags around important keywords and all numeric prices whenever appropriate
- Thai language only
- Keep the analysis usable for Telegram
- The final short_bias should be a compact trade call that is easy to send as a standalone message

Output structure:
- market_overview: overall read of the tape and positioning
- flow_summary: summarize call/put, IV, vol change, and future impulse
- key_levels: resistance/support levels with three tiers each when possible
- scenarios: bull / bear / sideway
- trade_view: short intraday trading view
- dte_context: DTE interpretation and its effect on confidence
- trend_note: short-term momentum comparison vs hour_ago and today_summary
- trade_plan: structured trade plan with direction, reason, entry, target, stop loss, invalidation, adjustment
- confidence: integer 0-100
- risk_level: Low / Medium / High
- short_bias: a compact final bias message in Thai that can be sent as-is

Important:
- market_overview must always mention comparison vs hour_ago and today_summary when available
- scenarios must stay consistent with trade_plan
- If there is no hour_ago or today_summary, say so explicitly
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "market_overview": {
            "type": "string",
            "description": "ภาพรวมตลาด: เทียบ Put vs Call volume, ราคา, โมเมนตัม, IV, Vol Chg และการเปลี่ยนแปลงเทียบ hour_ago / today_summary",
        },
        "flow_summary": {
            "type": "string",
            "description": "สรุป flow แบบสั้น: Call/Put, IV, Vol Chg, Future Chg และนัยต่อ momentum",
        },
        "key_levels": {
            "type": "object",
            "properties": {
                "resistance_far": {"type": "string", "description": "แนวต้านไกล"},
                "resistance_main": {"type": "string", "description": "แนวต้านหลัก"},
                "resistance_now": {"type": "string", "description": "แนวต้านปัจจุบัน"},
                "support_now": {"type": "string", "description": "แนวรับปัจจุบัน"},
                "support_main": {"type": "string", "description": "แนวรับหลัก"},
                "support_deep": {"type": "string", "description": "แนวรับลึก"},
            },
            "required": [
                "resistance_far",
                "resistance_main",
                "resistance_now",
                "support_now",
                "support_main",
                "support_deep",
            ],
        },
        "scenarios": {
            "type": "object",
            "properties": {
                "bull_case": {"type": "string", "description": "กรณีทะลุแนวต้าน"},
                "bear_case": {"type": "string", "description": "กรณีหลุดแนวรับ"},
                "sideway_case": {"type": "string", "description": "กรณีแกว่งสะสมกำลัง"},
            },
            "required": ["bull_case", "bear_case", "sideway_case"],
        },
        "trade_view": {
            "type": "string",
            "description": "มุมมองการเทรดระยะสั้น: ราคาปัจจุบันเทียบกับโซนสำคัญ, จังหวะเข้าที่แนะนำ",
        },
        "dte_context": {
            "type": "string",
            "description": "อธิบายสั้นๆ ว่า DTE ปัจจุบันอยู่ในโซนไหน และมีผลต่อความน่าเชื่อถือของโซนแนวรับ-แนวต้านอย่างไร",
        },
        "trend_note": {
            "type": "string",
            "description": "เปรียบเทียบ current vs hour_ago และ current vs today_summary",
        },
        "trade_plan": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "Long, Short หรือ Wait",
                },
                "reason": {"type": "string", "description": "เหตุผลสั้นๆ สำหรับ bias"},
                "entry": {"type": "string", "description": "จุดเข้า"},
                "target": {"type": "string", "description": "เป้าหมาย"},
                "stop_loss": {"type": "string", "description": "จุดยอม"},
                "invalid_if": {"type": "string", "description": "เงื่อนไขที่ทำให้มุมมองนี้ใช้ไม่ได้"},
                "adjustment": {"type": "string", "description": "วิธีแก้หากผิดทางหรือหลุด stop"},
            },
            "required": [
                "direction",
                "reason",
                "entry",
                "target",
                "stop_loss",
                "invalid_if",
                "adjustment",
            ],
        },
        "confidence": {
            "type": "integer",
            "description": "ความมั่นใจ 0-100",
        },
        "risk_level": {
            "type": "string",
            "description": "ระดับความเสี่ยง Low / Medium / High",
        },
        "short_bias": {
            "type": "string",
            "description": "ข้อความสั้นสำหรับส่งเป็น bias ฟันธงแบบ standalone",
        },
    },
    "required": [
        "market_overview",
        "flow_summary",
        "key_levels",
        "scenarios",
        "trade_view",
        "dte_context",
        "trend_note",
        "trade_plan",
        "confidence",
        "risk_level",
        "short_bias",
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
