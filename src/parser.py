"""
parser.py
=========
แปลง raw dict จาก scraper.py -> dict ที่ตรงกับ schema table `options_flow_snapshots`
"""

import re

class ParseError(Exception):
    pass

_NUM = r"-?[\d,]+(?:\.\d+)?"

PATTERNS = {
    "put_volume": re.compile(rf"Put:.*?>\s*({_NUM})"),
    "call_volume": re.compile(rf"Call:.*?>\s*({_NUM})"),
    "vol": re.compile(rf"(?<!Chg)Vol:.*?>\s*({_NUM})"),
    "vol_chg": re.compile(rf"Vol Chg:.*?>\s*({_NUM})"),
    "future_chg": re.compile(rf"Future Chg:.*?>\s*({_NUM})"),
}

# DTE ปรากฏในรูปแบบ "(0.22 DTE)" ใน page heading เช่น
# "Gold (OG|GC) G2RN6 (0.22 DTE) vs 4115.7 (+33.3) - Intraday Volume"
DTE_PATTERN = re.compile(rf"\(({_NUM})\s*DTE\)", re.IGNORECASE)

def _extract_number(pattern: re.Pattern, text: str) -> float | None:
    m = pattern.search(text)
    if not m:
        return None
    val = next(g for g in m.groups() if g is not None)
    return float(val.replace(",", ""))

def parse(raw: dict) -> dict:
    if not raw.get("charts"):
        raise ParseError("raw data ไม่มี charts เลย")

    chart = raw["charts"][0] 
    subtitle = chart.get("subtitle") or ""

    delta_levels = {}
    future_price = None
    contract = chart.get("title")

    for pl in chart.get("plotLines", []):
        label = pl.get("label") or ""
        value = pl.get("value")
        if label.startswith("Future:"):
            future_price = value
        elif label:
            delta_levels[label] = value

    put_volume = _extract_number(PATTERNS["put_volume"], subtitle)
    call_volume = _extract_number(PATTERNS["call_volume"], subtitle)
    vol = _extract_number(PATTERNS["vol"], subtitle)
    vol_chg = _extract_number(PATTERNS["vol_chg"], subtitle)
    future_chg = _extract_number(PATTERNS["future_chg"], subtitle)

    # DTE: ลองดึงจาก page_heading ก่อน (ที่ที่มันอยู่จริงตาม screenshot ตัวอย่าง)
    # ถ้าไม่เจอ fallback ไปหาใน subtitle/title เผื่อโครงหน้าเปลี่ยน
    dte = None
    for text in (raw.get("page_heading"), subtitle, contract):
        if not text:
            continue
        m = DTE_PATTERN.search(text)
        if m:
            dte = float(m.group(1).replace(",", ""))
            break

    missing = [k for k, v in {
        "future_price": future_price,
        "put_volume": put_volume,
        "call_volume": call_volume,
    }.items() if v is None]
    if missing:
        raise ParseError(f"ดึงค่าไม่ครบ: {missing}")

    return {
        "contract": contract,
        "dte": dte,
        "future_price": future_price,
        "future_chg": future_chg,
        "put_volume": int(put_volume) if put_volume is not None else None,
        "call_volume": int(call_volume) if call_volume is not None else None,
        "vol": vol,
        "vol_chg": vol_chg,
        "delta_levels": delta_levels,
        "raw_series": chart.get("series", []),
        "screenshot": raw.get("screenshot"),
    }

if __name__ == "__main__":
    import json
    import sys
    from scraper import scrape

    raw = scrape()
    parsed = parse(raw)
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
