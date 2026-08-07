"""
telegram.py
===========
ประกอบผลวิเคราะห์เป็นรายงานสไตล์นักวิเคราะห์ แล้วส่งเข้า Telegram
ผ่าน Bot API ตรงๆ (ใช้ requests ไม่ต้องพึ่ง library เพิ่ม)

ยังคงรูปแบบการส่งเดิม:
1) รูป
2) วิเคราะห์ละเอียด
3) สรุปสั้นพร้อมเทรด

ต้องมี:
- TELEGRAM_BOT_TOKEN  -> จาก BotFather
- TELEGRAM_CHAT_ID    -> chat/channel/group id ที่จะส่งเข้า (รองรับหลาย ID คั่นด้วยลูกน้ำ)
"""

import os
import time
from datetime import datetime, timezone, timedelta

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_API = "https://api.telegram.org/bot{token}/sendPhoto"

THAI_MONTHS = [
    "",
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
]

BANGKOK_TZ = timezone(timedelta(hours=7))


def _thai_datetime_str(dt: datetime | None = None) -> str:
    dt = (dt or datetime.now(timezone.utc)).astimezone(BANGKOK_TZ)
    buddhist_year = dt.year + 543
    return f"วันที่ {dt.day} {THAI_MONTHS[dt.month]} {buddhist_year} | เวลา {dt.strftime('%H:%M')} น."


def _safe_get(d: dict, key: str, default: str = "-") -> str:
    val = d.get(key, default) if isinstance(d, dict) else default
    return default if val in (None, "") else str(val)


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

    key_levels = ai_result.get("key_levels", {}) or {}
    scenarios = ai_result.get("scenarios", {}) or {}
    trade_plan = ai_result.get("trade_plan", {}) or {}

    confidence = ai_result.get("confidence", "-")
    risk_level = ai_result.get("risk_level", "-")

    return (
        f"📊 <b>รายงาน Volatility & Options Flow (Gold)</b>{dte_line}\n"
        f"{header}\n\n"
        f"<b>• ภาพรวมตลาด</b>\n{_safe_get(ai_result, 'market_overview')}\n\n"
        f"<b>• Flow Summary</b>\n{_safe_get(ai_result, 'flow_summary')}\n\n"
        f"<b>• โซนสำคัญ</b>\n"
        f"แนวต้านไกล: {_safe_get(key_levels, 'resistance_far')}\n"
        f"แนวต้านหลัก: {_safe_get(key_levels, 'resistance_main')}\n"
        f"แนวต้านปัจจุบัน: {_safe_get(key_levels, 'resistance_now')}\n"
        f"แนวรับปัจจุบัน: {_safe_get(key_levels, 'support_now')}\n"
        f"แนวรับหลัก: {_safe_get(key_levels, 'support_main')}\n"
        f"แนวรับลึก: {_safe_get(key_levels, 'support_deep')}\n\n"
        f"<b>• Scenario</b>\n"
        f"<b>Bull Case</b>\n{_safe_get(scenarios, 'bull_case')}\n\n"
        f"<b>Bear Case</b>\n{_safe_get(scenarios, 'bear_case')}\n\n"
        f"<b>Sideway Case</b>\n{_safe_get(scenarios, 'sideway_case')}\n\n"
        f"<b>• มุมมองการเทรดระยะสั้น</b>\n{_safe_get(ai_result, 'trade_view')}\n\n"
        f"<b>• DTE Context</b>\n{_safe_get(ai_result, 'dte_context')}\n\n"
        f"<b>• Trend Note</b>\n{_safe_get(ai_result, 'trend_note')}\n\n"
        f"<b>• Trade Plan</b>\n"
        f"Bias: {_safe_get(trade_plan, 'direction')}\n"
        f"เหตุผล: {_safe_get(trade_plan, 'reason')}\n"
        f"Entry: {_safe_get(trade_plan, 'entry')}\n"
        f"Target: {_safe_get(trade_plan, 'target')}\n"
        f"Stop Loss: {_safe_get(trade_plan, 'stop_loss')}\n"
        f"Invalid if: {_safe_get(trade_plan, 'invalid_if')}\n"
        f"Adjustment: {_safe_get(trade_plan, 'adjustment')}\n\n"
        f"<b>• Confidence / Risk</b>\n"
        f"Confidence: {confidence}\n"
        f"Risk Level: {risk_level}"
    )


def format_short_bias(ai_result: dict) -> str:
    if "error" in ai_result:
        return f"🎯 <b>Bias ฟันธง!</b>\nAI analysis error: {ai_result['error']}"

    short_bias = ai_result.get("short_bias")
    if short_bias:
        return f"🎯 <b>Bias ฟันธง!</b>\n{short_bias}"

    trade_plan = ai_result.get("trade_plan", {}) or {}
    return (
        f"🎯 <b>Bias ฟันธง!</b>\n"
        f"Bias: {_safe_get(trade_plan, 'direction')}\n"
        f"Entry: {_safe_get(trade_plan, 'entry')} | Target: {_safe_get(trade_plan, 'target')} | SL: {_safe_get(trade_plan, 'stop_loss')}\n"
        f"Reason: {_safe_get(trade_plan, 'reason')}"
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
            raise RuntimeError(
                "ไม่มี chat_ids ให้ส่ง — ทั้ง customers table (Supabase) และ "
                "TELEGRAM_CHAT_ID (env) ว่างเปล่าทั้งคู่"
            )
        chat_ids = [cid.strip() for cid in chat_ids_env.split(",") if cid.strip()]

    if not chat_ids:
        print("⚠️  ไม่มี chat_id ให้ส่ง (ข้ามขั้นตอนนี้)")
        return

    detailed_text = format_message(parsed, ai_result)
    short_bias_message = format_short_bias(ai_result)

    for cid in chat_ids:
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

        try:
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": detailed_text, "parse_mode": "HTML"},
                timeout=15,
            )
        except Exception as e:
            print(f"❌ ส่งวิเคราะห์ละเอียด ไปยัง ID: {cid} ล้มเหลว: {e}")
        time.sleep(0.5)

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
