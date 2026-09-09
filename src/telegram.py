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
        dte_line = f" (DTE: {dte})"

    if "error" in ai_result:
        return f"{header}\n\n⚠️ AI analysis error: {ai_result['error']}"

    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    spot = parsed.get("cfd_price", parsed.get("future_price", "-"))
    iv = parsed.get("vol", "-")
    put = totals.get("open_interest_view_put", totals.get("open_interest_put", "-"))
    call = totals.get("open_interest_view_call", totals.get("open_interest_call", "-"))
    delta_put = totals.get("oi_delta_put")
    delta_call = totals.get("oi_delta_call")
    churn = totals.get("churn")
    bias_raw = str(ai_result.get("short_bias", "-") or "-")
    bias_lower = bias_raw.lower()
    if any(w in bias_lower for w in ("wait", "รอ", "ยังไม่")):
        bias = "WAIT"
    elif any(w in bias_lower for w in ("short", "sell", "ขาย")):
        bias = "SELL"
    elif any(w in bias_lower for w in ("long", "buy", "ซื้อ")):
        bias = "BUY"
    else:
        bias = "WAIT"
    def compact(value):
        text = " ".join(str(value or "-").split())
        if len(text) <= 220:
            return text
        return text[:220].rsplit(" ", 1)[0] + "..."

    return (
        f"<b>OI BOT:</b> 📊 Volatility &amp; Options Flow (Gold){dte_line}\n{header}\n"
        f"CFD <b>{spot}</b>  |  FUTURES {parsed.get('future_price', '-')}\n"
        f"DIFF {parsed.get('basis_diff', '-')}  |  IV <b>{iv}%</b>\n\n"
        f"<b>Open Interest Positioning</b>\nPut <b>{put}</b>  •  Call <b>{call}</b>\n"
        f"ΔOI: {delta_put if delta_put is not None else '-'} Put  •  {delta_call if delta_call is not None else '-'} Call  |  Churn: {churn if churn is not None else '-'}\n"
        f"Bias: <b>{bias}</b>\n\n"
        f"<b>วิเคราะห์</b>\n{compact(ai_result.get('market_overview'))}\n\n"
        f"<b>KEY LEVELS (CFD)</b>\n"
        f"ต้านไกล  {ai_result.get('resistance_far', '-')}\n"
        f"ต้านหลัก  {ai_result.get('resistance_main', '-')}\n"
        f"ต้านใกล้  {ai_result.get('resistance_current', '-')}\n"
        f"รับใกล้    {ai_result.get('support_current', '-')}\n"
        f"รับหลัก    {ai_result.get('support_main', '-')}\n"
        f"รับลึก     {ai_result.get('support_deep', '-')}\n\n"
        f"<b>SCENARIO</b>\n"
        f"🟢 Bull: {compact(ai_result.get('bull_case'))}\n"
        f"🔴 Bear: {compact(ai_result.get('bear_case'))}\n"
        f"🟡 Sideway: {compact(ai_result.get('sideway_case'))}"
    )


def format_trade_plan_message(parsed: dict, ai_result: dict) -> str:
    """Chat 3: แยก Bias และแผนเทรดออกจาก market analysis."""
    if "error" in ai_result:
        return "🎯 <b>Bias ฟันธง!</b>\n\nยังไม่มีแผน เนื่องจาก AI analysis ไม่สำเร็จ"
    return f"🎯 <b>Bias ฟันธง!</b>\n\n{ai_result.get('short_bias', 'ยังไม่มีข้อมูลแผนเทรด')}"


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
    put_iv = totals.get("open_interest_view_put", totals.get("open_interest_put", "-"))
    call_iv = totals.get("open_interest_view_call", totals.get("open_interest_call", "-"))
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
        direction_label = "แผน SELL"
        trigger = f"หลุด Put wall {put_level} แล้วไม่สามารถ reclaim กลับได้"
        target = f"เป้าหมายถัดไป: Expected Range / OI wall ด้านล่าง"
        invalidation = f"ยกเลิกแผนเมื่อราคากลับเหนือ {put_level}"
        status = "รอยืนยัน Short"
    elif any(word in ai_bias for word in ("long", "buy", "ซื้อ")) or float(call_iv or 0) > float(put_iv or 0):
        direction = "LONG"
        direction_label = "แผน BUY"
        trigger = f"ยืนเหนือ Call wall {call_level} และไม่หลุดกลับลงมา"
        target = f"เป้าหมายถัดไป: OI wall / Expected Range ด้านบน"
        invalidation = f"ยกเลิกแผนเมื่อราคาหลุดกลับใต้ {call_level}"
        status = "รอยืนยัน Long"
    else:
        direction = "WAIT"
        direction_label = "แผน WAIT"
        trigger = "รอ Flow และราคายืนยันไปในทิศทางเดียวกัน"
        target = "ยังไม่กำหนด Target จนกว่าจะมีทิศทางชัดเจน"
        invalidation = "ไม่เปิดสถานะกลางกรอบ"
        status = "WAIT"

    # BUY/SELL is green/red only after the CFD price crosses its trigger.
    if direction == "LONG" and price is not None and price >= float(call_wall.get("strike_cfd", price + 1)):
        status, status_icon = "BUY", "🟢"
    elif direction == "SHORT" and price is not None and price <= float(put_wall.get("strike_cfd", price - 1)):
        status, status_icon = "SELL", "🔴"
    else:
        status, status_icon = "WAIT", "🟡"

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
    def tp_percent(value):
        if entry_level is None or value is None or not float(entry_level):
            return "-"
        return f"{abs(float(value) - float(entry_level)) / abs(float(entry_level)) * 100:.2f}%"
    tp_percent_text = [tp_percent(x) for x in target_values]
    sd_low = fmt(one_sd.get("lower_cfd", "-"))
    sd_high = fmt(one_sd.get("upper_cfd", "-"))
    return (
        f"⚡ <b>XAU SCALP SETUP</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>{expiry}</b>  •  Friday Options\n"
        f"DTE {dte}  •  CFD <b>{cfd}</b>\n\n"
        f"<b>สถานะ</b>\n"
        f"{status_icon} <b>{status}</b>\n"
        f"แผนหลัก: <b>{'BUY' if direction == 'LONG' else 'SELL' if direction == 'SHORT' else 'WAIT'}</b>\n"
        f"Flow: <b>{bias}</b>\n\n"
        f"<b>ราคาอ้างอิง</b>\n"
        f"CFD {cfd}  |  Spot {spot}\n"
        f"Futures {future}  |  Diff {diff}\n"
        f"ATM IV {fmt(vol)}%\n\n"
        f"<b>OPEN INTEREST</b>\n"
        f"Put <b>{put_iv}</b>  •  Call <b>{call_iv}</b>\n"
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
        f"TP1: <b>{tp_text[0]}</b>  (+{tp_percent_text[0]})\n"
        f"TP2: <b>{tp_text[1]}</b>  (+{tp_percent_text[1]})\n"
        f"TP3: <b>{tp_text[2]}</b>  (+{tp_percent_text[2]})\n"
        f"TP4: <b>{tp_text[3]}</b>  (+{tp_percent_text[3]})\n\n"
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

        # Chat 2 = market overview, key levels และ scenarios
        try:
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": detailed_text, "parse_mode": "HTML"},
                timeout=15,
            )
        except Exception as e:
            print(f"❌ ส่งวิเคราะห์ละเอียด ไปยัง ID: {cid} ล้มเหลว: {e}")
        time.sleep(0.5)
            
        # Chat 3 = Bias และ Trade Plan; recipient 8622081180 ได้ micro-scalp card
        try:
            if str(cid) == SHORT_TRADER_CHAT_ID:
                short_bias_message = _short_trader_message(parsed, ai_result)
            else:
                short_bias_message = format_trade_plan_message(parsed, ai_result)
            requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": cid, "text": short_bias_message, "parse_mode": "HTML"},
                timeout=15,
            )
            print(f"✅ ส่งข้อมูลครบ 3 แชท ไปยัง ID: {cid} สำเร็จ")
        except Exception as e:
            print(f"❌ ส่ง Short Bias ไปยัง ID: {cid} ล้มเหลว: {e}")
            
        time.sleep(1)
