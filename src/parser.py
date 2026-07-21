"""
parser.py
=========
แปลง raw dict จาก scraper.py -> dict ที่ตรงกับ schema table `options_flow_snapshots`

หมายเหตุ: ตัวเลข Put/Call/Vol/Vol Chg/Future Chg มักถูกฝังเป็น subtitle text
(รูปแบบ HTML span) ในตัว chart เช่น:
  "Put: 523  Call: 714  Vol: 25.17  Vol Chg: 0.06  Future Chg: 57.8"
ฟังก์ชันนี้ regex ดึงตัวเลขจาก pattern นั้น — ถ้า CME เปลี่ยน format ต้องแก้ regex ตรงนี้
"""

import re


class ParseError(Exception):
    pass


_NUM = r"-?\d+(?:\.\d+)?"

PATTERNS = {
    "put_volume": re.compile(rf"Put:\s*</span>\s*({_NUM})|Put:\s*({_NUM})"),
    "call_volume": re.compile(rf"Call:\s*</span>\s*({_NUM})|Call:\s*({_NUM})"),
    "vol": re.compile(rf"Vol:\s*</span>\s*({_NUM})|(?<!Chg)Vol:\s*({_NUM})"),
    "vol_chg": re.compile(rf"Vol Chg:.*?({_NUM})"),
    "future_chg": re.compile(rf"Future Chg:.*?({_NUM})"),
}


def _extract_number(pattern: re.Pattern, text: str) -> float | None:
    m = pattern.search(text)
    if not m:
        return None
    val = next(g for g in m.groups() if g is not None)
    return float(val)


def parse(raw: dict) -> dict:
    if not raw.get("charts"):
        raise ParseError("raw data ไม่มี charts เลย — ตรวจสอบ scraper output")

    chart = raw["charts"][0]  # หน้า Vol2Vol มักมี chart หลักตัวเดียว
    subtitle = chart.get("subtitle") or ""

    # --- delta levels + future price จาก plotLines ---
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

    # --- summary stats จาก subtitle text ---
    put_volume = _extract_number(PATTERNS["put_volume"], subtitle)
    call_volume = _extract_number(PATTERNS["call_volume"], subtitle)
    vol = _extract_number(PATTERNS["vol"], subtitle)
    vol_chg = _extract_number(PATTERNS["vol_chg"], subtitle)
    future_chg = _extract_number(PATTERNS["future_chg"], subtitle)

    missing = [k for k, v in {
        "future_price": future_price,
        "put_volume": put_volume,
        "call_volume": call_volume,
    }.items() if v is None]
    if missing:
        raise ParseError(
            f"ดึงค่าไม่ครบ: {missing} — โครง subtitle/plotLines อาจเปลี่ยนไป "
            f"(raw subtitle: {subtitle[:200]!r})"
        )

    return {
        "contract": contract,
        "future_price": future_price,
        "future_chg": future_chg,
        "put_volume": int(put_volume) if put_volume is not None else None,
        "call_volume": int(call_volume) if call_volume is not None else None,
        "vol": vol,
        "vol_chg": vol_chg,
        "delta_levels": delta_levels,
        "raw_series": chart.get("series", []),
    }


if __name__ == "__main__":
    import json
    import sys
    from scraper import scrape

    raw = scrape()
    parsed = parse(raw)
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
