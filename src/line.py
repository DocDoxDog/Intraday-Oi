"""
line.py
=======
ส่งรายงานเข้า LINE Official Account แบบ Broadcast
(ส่งหาทุกคนที่แอดเพื่อนกับ OA — ไม่ต้องมี userId รายคน, ใช้แค่ Channel Access Token)

หมายเหตุ:
- Broadcast API ของ LINE ฟรี 500 ข้อความ/เดือน (บน Free plan) แล้วเริ่มคิดเงินตาม
  แพ็กเกจ Messaging API — เช็คโควตาใน LINE Official Account Manager ก่อนใช้งานจริง
- ต้องสร้าง LINE Official Account + Messaging API channel ใน LINE Developers Console
  แล้วเอา "Channel access token (long-lived)" มาใส่ใน LINE_CHANNEL_ACCESS_TOKEN
"""

import os
import time
import requests

LINE_BROADCAST_API = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

# LINE จำกัดสูงสุด 5 message objects ต่อ 1 คำขอ broadcast
MAX_MESSAGES_PER_REQUEST = 5


def _text_message(text: str) -> dict:
    # LINE จำกัดความยาวข้อความ text ที่ 5000 ตัวอักษร/ก้อน
    return {"type": "text", "text": text[:5000]}


def _image_message(url: str) -> dict:
    return {
        "type": "image",
        "originalContentUrl": url,
        "previewImageUrl": url,
    }


def format_message(parsed: dict, ai_result: dict) -> str:
    dte = parsed.get("dte")
    dte_line = ""
    if dte is not None:
        if str(dte).startswith("0."):
            dte_line = f" (INTRADAY | DTE: {dte})"
        else:
            dte_line = f" (DTE: {dte})"

    if "error" in ai_result:
        return f"⚠️ AI analysis error: {ai_result['error']}"

    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    spot = parsed.get("cfd_price", parsed.get("future_price", "-"))
    iv = parsed.get("vol", "-")
    put = totals.get("open_interest_view_put", totals.get("open_interest_put", "-"))
    call = totals.get("open_interest_view_call", totals.get("open_interest_call", "-"))
    delta_put = totals.get("oi_delta_put", "-")
    delta_call = totals.get("oi_delta_call", "-")
    churn = totals.get("churn", "-")
    def compact(value):
        text = " ".join(str(value or "-").split())
        if len(text) <= 220:
            return text
        return text[:220].rsplit(" ", 1)[0] + "..."
    rows = raw.get("cfd_strike_rows") or []
    try:
        price = float(spot)
    except (TypeError, ValueError):
        price = None
    puts = [r for r in rows if r.get("strike_cfd") is not None and (r.get("oiPut") or 0) > 0]
    calls = [r for r in rows if r.get("strike_cfd") is not None and (r.get("oiCall") or 0) > 0]
    put_wall = max((r for r in puts if price is not None and float(r["strike_cfd"]) < price), key=lambda r: float(r["strike_cfd"]), default=None)
    call_wall = min((r for r in calls if price is not None and float(r["strike_cfd"]) > price), key=lambda r: float(r["strike_cfd"]), default=None)
    ai_bias = str(ai_result.get("short_bias") or "").lower()
    is_short = any(w in ai_bias for w in ("short", "sell", "ขาย"))
    is_long = any(w in ai_bias for w in ("long", "buy", "ซื้อ")) or (not is_short and float(call or 0) > float(put or 0))
    direction = "SELL" if is_short else "BUY" if is_long else "WAIT"
    wall = put_wall if direction == "SELL" else call_wall if direction == "BUY" else None
    if wall:
        entry = float(wall["strike_cfd"])
        stop = entry + 30 if direction == "SELL" else entry - 30
        tps = [entry + (x if direction == "BUY" else -x) for x in (20, 40, 60, 90)]
        confirmed = price is not None and (price <= entry if direction == "SELL" else price >= entry)
        status = ("🟢 BUY" if direction == "BUY" and confirmed else "🔴 SELL" if direction == "SELL" and confirmed else "🟡 WAIT")
        plan = f"{status} | Entry {entry:.2f} | SL {stop:.2f}\n" + " | ".join(f"TP{i} {tp:.2f} (+{abs(tp-entry)/entry*100:.2f}%)" for i, tp in enumerate(tps, 1))
    else:
        plan = "🟡 WAIT | รอทิศทางและระดับยืนยันก่อนเปิดสถานะ"
    return (
        f"📊 Gold Options Flow{dte_line}\n\n"
        f"สรุป: CFD {spot} | IV {iv}%\n"
        f"Open Interest: Put {put} | Call {call}\n"
        f"ΔOI: Put {delta_put} | Call {delta_call} | Churn {churn}\n"
        f"Bias: {ai_result.get('short_bias', '-')}\n\n"
        f"วิเคราะห์\n{compact(ai_result.get('market_overview'))}\n\n"
        f"KEY LEVELS (CFD)\n"
        f"ต้านไกล: {ai_result.get('resistance_far', '-')}\n"
        f"ต้านหลัก: {ai_result.get('resistance_main', '-')}\n"
        f"ต้านใกล้: {ai_result.get('resistance_current', '-')}\n"
        f"รับใกล้: {ai_result.get('support_current', '-')}\n"
        f"รับหลัก: {ai_result.get('support_main', '-')}\n"
        f"รับลึก: {ai_result.get('support_deep', '-')}\n\n"
        f"TRADE PLAN (ภาพใหญ่ / CFD)\n{plan}\n\n"
        f"แผน\n"
        f"Bull: {compact(ai_result.get('bull_case'))}\n"
        f"Bear: {compact(ai_result.get('bear_case'))}\n"
        f"มุมมอง: {compact(ai_result.get('sideway_case'))}"
    )


def _post_broadcast(token: str, messages: list[dict]) -> None:
    resp = requests.post(
        LINE_BROADCAST_API,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"messages": messages},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LINE broadcast ล้มเหลว [{resp.status_code}]: {resp.text}")


def _post_push(token: str, to: str, messages: list[dict]) -> None:
    resp = requests.post(
        LINE_PUSH_API,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"to": to, "messages": messages},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LINE group push ล้มเหลว [{resp.status_code}]: {resp.text}")


def send(parsed: dict, ai_result: dict, screenshot_url: str | None = None) -> None:
    """
    ส่ง broadcast ไปหาผู้ที่แอดเพื่อน LINE OA ทุกคน
    ไม่ต้องรู้ userId รายคน — LINE จัดการกระจายให้เองตาม Channel access token
    """
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN ไม่ได้ตั้งค่า — เช็ค GitHub Secrets หรือไฟล์ .env")

    detailed_text = format_message(parsed, ai_result)
    bias_text = ai_result.get("short_bias", "ไม่มีข้อมูล Bias")
    short_bias_message = f"🎯 Bias ฟันธง!\n{bias_text}"

    messages: list[dict] = []
    if screenshot_url:
        messages.append(_image_message(screenshot_url))
    messages.append(_text_message(detailed_text))
    messages.append(_text_message(short_bias_message))

    # Broadcast ไปยังผู้ติดตาม/ผู้ที่แชทกับ OA ตามเงื่อนไขของ LINE
    errors: list[str] = []
    for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
        chunk = messages[i : i + MAX_MESSAGES_PER_REQUEST]
        try:
            _post_broadcast(token, chunk)
            print(f"✅ ส่ง LINE broadcast สำเร็จ ({len(chunk)} ข้อความ)")
        except Exception as e:
            print(f"❌ ส่ง LINE broadcast ล้มเหลว: {e}")
            errors.append(str(e))
        time.sleep(0.5)

    # Push ข้อความชุดเดียวกันเข้า Group แยกจาก Broadcast
    group_id = os.environ.get("LINE_GROUP_ID", "").strip()
    if group_id:
        for i in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
            chunk = messages[i : i + MAX_MESSAGES_PER_REQUEST]
            try:
                _post_push(token, group_id, chunk)
                print(f"✅ ส่ง LINE group push สำเร็จ ({len(chunk)} ข้อความ)")
            except Exception as e:
                print(f"❌ ส่ง LINE group push ล้มเหลว: {e}")
                errors.append(str(e))
            time.sleep(0.5)
    else:
        print("⏭️  ข้าม LINE group push (ไม่ได้ตั้งค่า LINE_GROUP_ID)")

    # ถ้ามี chunk ไหนล้มเหลว ให้ raise ออกไปจริง — กัน main.py print "✅ Sent to LINE"
    # ทั้งที่จริงๆ ส่งไม่สำเร็จ (ก่อนหน้านี้ error ถูกกลืนไว้เงียบๆ ในนี้)
    if errors:
        raise RuntimeError(f"LINE broadcast ล้มเหลว {len(errors)}/{ (len(messages) + MAX_MESSAGES_PER_REQUEST - 1) // MAX_MESSAGES_PER_REQUEST } chunk(s): " + " | ".join(errors))
