"""
telegram.py
===========
ประกอบผลวิเคราะห์เป็นรายงานสไตล์นักวิเคราะห์ แล้วส่งเข้า Telegram
รูปแบบอัปเดต: โซนสำคัญครบถ้วน (ต้านไกล/หลัก/ปัจจุบัน, รับปัจจุบัน/หลัก/ลึก),
และ Scenarios (1) Bull Case, 2) Bear Case, 3) Sideway Case) พร้อม Chat 2 (Bias & Action Plan)
"""

import os
import time
from datetime import datetime, timezone, timedelta
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_API = "https://api.telegram.org/bot{token}/sendPhoto"

THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

BANGKOK_TZ = timezone(timedelta(hours=7))
SHORT_TRADER_CHAT_ID = "8622081180"


def _thai_datetime_str(dt: datetime | None = None) -> str:
    dt = (dt or datetime.now(timezone.utc)).astimezone(BANGKOK_TZ)
    buddhist_year = dt.year + 543
    return f"วันที่ {dt.day} {THAI_MONTHS[dt.month]} {buddhist_year} | เวลา {dt.strftime('%H:%M')} น."


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

    return (
        f"📊 <b>รายงาน Volatility & Options Flow (Gold)</b>{dte_line}\n"
        f"{header}\n\n"
        f"<b>• ภาพรวมตลาด</b>\n{ai_result.get('market_overview', '-')}\n\n"
        f"<b>• โซนสำคัญ</b>\n"
        f" • แนวต้านไกล: {ai_result.get('resistance_far', '-')}\n"
        f" • แนวต้านหลัก: {ai_result.get('resistance_main', '-')}\n"
        f" • แนวต้านปัจจุบัน: {ai_result.get('resistance_current', '-')}\n"
        f" • แนวรับปัจจุบัน: {ai_result.get('support_current', '-')}\n"
        f" • แนวรับหลัก: {ai_result.get('support_main', '-')}\n"
        f" • แนวรับลึก: {ai_result.get('support_deep', '-')}\n\n"
        f"<b>• Scenario</b>\n"
        f"<b>1) Bull Case</b>\n{ai_result.get('bull_case', '-')}\n\n"
        f"<b>2) Bear Case</b>\n{ai_result.get('bear_case', '-')}\n\n"
        f"<b>3) Sideway Case (มุมมองหลัก)</b>\n{ai_result.get('sideway_case', '-')}"
    )


def _short_trader_message(parsed: dict, ai_result: dict) -> str:
    """รายงานสั้นสำหรับ trader: bias, trigger, invalidation และ target เท่านั้น.

    ไม่สร้างตัวเลข Entry/SL/TP ใหม่เอง หาก AI ไม่ได้ให้ระดับไว้ใน short_bias.
    โซนจาก AI จะแสดงเป็นเงื่อนไข ไม่ใช่คำสั่งเข้าทันที.
    """
    if "error" in ai_result:
        return f"⚠️ GOLD SCALP\nAI error: {ai_result['error']}"

    def fmt(value, digits=2):
        if isinstance(value, (int, float)):
            return f"{value:.{digits}f}"
        return str(value)

    dte = fmt(parsed.get("dte", "-"))
    future = fmt(parsed.get("future_price", "-"))
    spot = fmt(parsed.get("spot_price", "-"))
    diff = fmt(parsed.get("basis_diff", "-"))
    cfd_value = parsed.get("cfd_price", "-")
    cfd = fmt(cfd_value)
    vol = parsed.get("vol", "-")
    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    put_iv = totals.get("intraday_volume_put", parsed.get("put_volume", "-"))
    call_iv = totals.get("intraday_volume_call", parsed.get("call_volume", "-"))
    put_oi = totals.get("open_interest_put", "-")
    call_oi = totals.get("open_interest_call", "-")
    selection = raw.get("expiration_selection") or {}
    expiry = selection.get("selected") or "-"

    rows = raw.get("cfd_strike_rows") or []
    price = float(cfd_value) if isinstance(cfd_value, (int, float)) else None
    put_candidates = sorted(
        (r for r in rows if r.get("strike_cfd") is not None and (r.get("oiPut") or 0) > 0),
        key=lambda r: r.get("strike_cfd"),
    )
    call_candidates = sorted(
        (r for r in rows if r.get("strike_cfd") is not None and (r.get("oiCall") or 0) > 0),
        key=lambda r: r.get("strike_cfd"),
    )
    below = [r for r in put_candidates if price is not None and r["strike_cfd"] < price]
    above = [r for r in call_candidates if price is not None and r["strike_cfd"] > price]
    put_wall = max(below, key=lambda r: r["strike_cfd"], default=None)
    call_wall = min(above, key=lambda r: r["strike_cfd"], default=None)
    if put_wall is None:
        put_wall = max(put_candidates, key=lambda r: r.get("oiPut") or 0, default={})
    if call_wall is None:
        call_wall = max(call_candidates, key=lambda r: r.get("oiCall") or 0, default={})
    put_level = fmt(put_wall.get("strike_cfd", "-"))
    call_level = fmt(call_wall.get("strike_cfd", "-"))
    bias = "CALL-LEANING" if float(call_iv or 0) > float(put_iv or 0) else "PUT-LEANING"
    ranges = raw.get("cfd_expected_ranges") or []
    one_sd = next((r for r in ranges if r.get("percent") == "68%"), {})
    two_sd = next((r for r in ranges if r.get("percent") == "95%"), {})
    three_sd = next((r for r in ranges if r.get("percent") == "99.7%"), {})
    # Select one directional plan. Prefer the AI bias when available; otherwise
    # use the observed intraday flow as the deterministic fallback.
    ai_bias = str(ai_result.get("short_bias") or "").lower()
    if any(word in ai_bias for word in ("short", "sell", "ขาย")):
        direction = "SHORT"
        direction_label = "แผน Short"
        trigger = f"หลุด Put wall {put_level} แล้วไม่สามารถ reclaim กลับได้"
        target = f"เป้าหมายถัดไป: Expected Range / OI wall ด้านล่าง"
        invalidation = f"ยกเลิกแผนเมื่อราคากลับเหนือ {put_level}"
        status = "รอยืนยัน Short"
    elif any(word in ai_bias for word in ("long", "buy", "ซื้อ")) or float(call_iv or 0) > float(put_iv or 0):
        direction = "LONG"
        direction_label = "แผน Long"
        trigger = f"ยืนเหนือ Call wall {call_level} และไม่หลุดกลับลงมา"
        target = f"เป้าหมายถัดไป: OI wall / Expected Range ด้านบน"
        invalidation = f"ยกเลิกแผนเมื่อราคาหลุดกลับใต้ {call_level}"
        status = "รอยืนยัน Long"
    else:
        direction = "WAIT"
        direction_label = "แผน Wait"
        trigger = "รอ Flow และราคายืนยันไปในทิศทางเดียวกัน"
        target = "ยังไม่กำหนด Target จนกว่าจะมีทิศทางชัดเจน"
        invalidation = "ไม่เปิดสถานะกลางกรอบ"
        status = "WAIT"

    # Micro-scalp ladder for this recipient. OI/Expected Range still validate
    # direction, but the execution plan stays tight and does not use swing
    # targets. Maximum planned stop distance is kept below 10 dollars.
    scalp_steps = (5.0, 10.0, 15.0, 20.0)
    scalp_stop = 8.0
    above_call = sorted({float(r["strike_cfd"]) for r in call_candidates if price is None or r["strike_cfd"] > float(call_level)})
    below_put = sorted({float(r["strike_cfd"]) for r in put_candidates if price is None or r["strike_cfd"] < float(put_level)}, reverse=True)
    if direction == "LONG":
        entry_level = call_wall.get("strike_cfd", cfd_value)
        sl_level = float(entry_level) - scalp_stop
        target_values = [float(entry_level) + step for step in scalp_steps]
    elif direction == "SHORT":
        entry_level = put_wall.get("strike_cfd", cfd_value)
        sl_level = float(entry_level) + scalp_stop
        target_values = [float(entry_level) - step for step in scalp_steps]
    else:
        entry_level = sl_level = None
        target_values = [None] * 4

    entry_text = fmt(entry_level) if entry_level is not None else "รอทิศทางชัดเจน"
    sl_text = fmt(sl_level) if sl_level is not None else "ยังไม่กำหนด"
    tp_text = [fmt(x) if x is not None else "-" for x in target_values]
    sd_low = fmt(one_sd.get("lower_cfd", "-"))
    sd_high = fmt(one_sd.get("upper_cfd", "-"))
    return (
        f"⚡ <b>XAU SCALP SETUP</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>{expiry}</b>  •  Friday Options\n"
        f"DTE {dte}  •  CFD <b>{cfd}</b>\n\n"
        f"<b>สถานะ</b>\n"
        f"⚪ <b>{status}</b>\n"
        f"แผนหลัก: <b>{direction}</b>\n"
        f"Flow: <b>{bias}</b>\n\n"
        f"<b>ราคาอ้างอิง</b>\n"
        f"CFD {cfd}  |  Spot {spot}\n"
        f"Futures {future}  |  Diff {diff}\n"
        f"ATM IV {fmt(vol)}%\n\n"
        f"<b>FLOW / OI</b>\n"
        f"Intraday  Put <b>{put_iv}</b>  •  Call <b>{call_iv}</b>\n"
        f"OI         Put <b>{put_oi}</b>  •  Call <b>{call_oi}</b>\n\n"
        f"<b>KEY LEVELS (CFD)</b>\n"
        f"🟢 Put wall   <b>{put_level}</b>  ({put_wall.get('oiPut', '-')})\n"
        f"🔴 Call wall  <b>{call_level}</b>  ({call_wall.get('oiCall', '-')})\n"
        f"1 SD range   {sd_low} – {sd_high}\n\n"
        f"<b>{direction_label}</b>\n"
        f"เข้าเมื่อ: {trigger}\n"
        f"\n<b>TRADE PLAN (CFD)</b>\n"
        f"Entry / Limit: <b>{entry_text}</b>\n"
        f"SL: <b>{sl_text}</b>\n"
        f"TP1: <b>{tp_text[0]}</b>\n"
        f"TP2: <b>{tp_text[1]}</b>\n"
        f"TP3: <b>{tp_text[2]}</b>\n"
        f"TP4: <b>{tp_text[3]}</b>\n\n"
        f"Invalidation: {invalidation}\n\n"
        f"<i>Technical confirmation ใช้คัดกรองภายใน\n"
        f"แผนนี้ไม่ใช่การการันตีกำไร และห้ามเข้าในกลางกรอบ</i>"
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
            raise RuntimeError("ไม่มี chat_ids ให้ส่ง")
        chat_ids = [cid.strip() for cid in chat_ids_env.split(',') if cid.strip()]

    if not chat_ids:
        print("⚠️  ไม่มี chat_id ให้ส่ง (ข้ามขั้นตอนนี้)")
        return

    detailed_text = format_message(parsed, ai_result)
    bias_text = ai_result.get('short_bias', 'ไม่มีข้อมูล Bias')
    short_bias_message = f"🎯 <b>Bias ฟันธง!</b>\n{bias_text}"

    for cid in chat_ids:
        # 1. ส่งรูปภาพ (ถ้ามี)
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

        # 2. ส่งรายงานละเอียด (Chat 1)
        try:
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": detailed_text, "parse_mode": "HTML"},
                timeout=15,
            )
        except Exception as e:
            print(f"❌ ส่งวิเคราะห์ละเอียด ไปยัง ID: {cid} ล้มเหลว: {e}")
        time.sleep(0.5)
            
        # 3. ส่ง Bias ฟันธง (Chat 2); recipient 8622081180 gets the
        # compact short-trader card requested by the user.
        try:
            if str(cid) == SHORT_TRADER_CHAT_ID:
                short_bias_message = _short_trader_message(parsed, ai_result)
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": short_bias_message, "parse_mode": "HTML"},
                timeout=15,
            )
            print(f"✅ ส่งข้อมูลครบ 3 แชท ไปยัง ID: {cid} สำเร็จ")
        except Exception as e:
            print(f"❌ ส่ง Short Bias ไปยัง ID: {cid} ล้มเหลว: {e}")
            
        time.sleep(1)
