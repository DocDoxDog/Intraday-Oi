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


_BIAS_EMOJI = {"long": "🟢", "short": "🔴", "wait": "🟡"}


def _fmt_levels(levels) -> str:
    if not levels:
        return "-"
    lines = []
    for lv in levels:
        if isinstance(lv, dict):
            price = lv.get("price", "-")
            delta = lv.get("delta")
            lines.append(f"{price} ({delta})" if delta else str(price))
        else:
            lines.append(str(lv))
    return "\n".join(lines)


def _fmt_reasons(reasons) -> str:
    if not reasons:
        return "-"
    return "\n".join(f"• {r}" for r in reasons)


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

    trade_plan = ai_result.get("trade_plan", {}) or {}

    return (
        f"📈 <b>วิเคราะห์ตลาด</b>{dte_line}\n"
        f"{header}\n\n"
        f"🌍 <b>ภาพรวมตลาด</b>\n{_safe_get(ai_result, 'market_overview')}\n\n"
        f"🔍 <b>สิ่งที่ต้องจับตา</b>\n{_safe_get(ai_result, 'watch_insight')}\n\n"
        f"🎯 <b>โซนสำคัญ</b>\n"
        f"🔺 <b>แนวต้าน</b>\n{_fmt_levels(ai_result.get('resistance_levels'))}\n\n"
        f"🔻 <b>แนวรับ</b>\n{_fmt_levels(ai_result.get('support_levels'))}\n\n"
        f"📌 <b>Scenario</b>\n"
        f"🟢 Bull {_safe_get(ai_result, 'scenario_bull')}\n"
        f"🔴 Bear {_safe_get(ai_result, 'scenario_bear')}\n"
        f"🟡 Sideway {_safe_get(ai_result, 'scenario_sideway')}"
    )


def format_short_bias(ai_result: dict) -> str:
    if "error" in ai_result:
        return f"⚡ <b>สรุปพร้อมเทรด</b>\nAI analysis error: {ai_result['error']}"

    direction = _safe_get(ai_result, "bias_direction")
    emoji = _BIAS_EMOJI.get(direction.strip().lower(), "⚪️")
    trade_plan = ai_result.get("trade_plan", {}) or {}

    return (
        f"⚡ <b>สรุปพร้อมเทรด</b>\n\n"
        f"🎯 <b>Bias ฟันธง</b>\n"
        f"<b>{direction}</b> {emoji}\n\n"
        f"เหตุผล\n{_fmt_reasons(ai_result.get('bias_reasons'))}\n\n"
        f"📌 <b>แผนเทรด</b>\n"
        f"Entry {_safe_get(trade_plan, 'entry')}\n"
        f"TP {_safe_get(trade_plan, 'target')}\n"
        f"SL {_safe_get(trade_plan, 'stop_loss')}\n"
        f"Invalid {_safe_get(trade_plan, 'invalid')}"
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
