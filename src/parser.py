"""
parser.py
=========
แปลง raw dict จาก scraper.py เป็น schema เดิมของ options_flow_snapshots
พร้อมเก็บข้อมูล intraday ราย strike ทุกค่าที่ QuikStrike ส่งมาไว้ใน raw_series.
"""

from __future__ import annotations

import re
from typing import Any


class ParseError(Exception):
    pass


_NUM = r"-?[\d,]+(?:\.\d+)?"
DTE_PATTERN_STRICT = re.compile(
    rf"\(({_NUM})\s*DTE\)\s*vs\s*{_NUM}", re.IGNORECASE
)
DTE_PATTERN_LOOSE = re.compile(rf"\(({_NUM})\s*DTE\)", re.IGNORECASE)

_INT_FIELDS = {
    "oiCall", "oiPut", "oiTotal", "volumeCall", "volumePut", "volumeTotal",
    "ivolumeCall", "ivolumePut", "ivolumeTotal",
}
_FLOAT_FIELDS = {
    "callPremium", "putPremium", "straddlePremium", "callSettle", "putSettle",
    "straddleSettle", "callChange", "putChange", "straddleChange", "vol",
    "callDelta", "putDelta", "gamma", "vega", "theta", "oichgvCall",
    "oichgvPut", "oichgvTotal",
}
_CHANGE_FIELDS = {
    "oiCallChange", "oiPutChange", "oiTotalChange", "volumeCallChange",
    "volumePutChange", "volumeTotalChange",
}


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"no change", "n/a", "na", "null", "none"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _normalise_row(row: dict) -> dict:
    fields = dict(row.get("fields") or {})
    title = fields.get("title") or ""
    strike_match = re.search(rf"({_NUM})\s*Strike", title, re.IGNORECASE)
    strike = _number(strike_match.group(1)) if strike_match else None

    out: dict[str, Any] = {
        "strike": strike,
        "coords": row.get("coords"),
        "template_id": row.get("template_id"),
    }
    # Keep every field, including show/hide class flags, so no information from
    # QuikStrike's tooltip payload is silently discarded.
    for key, value in fields.items():
        if key in _INT_FIELDS:
            out[key] = _number(value)
        elif key in _FLOAT_FIELDS or key in _CHANGE_FIELDS:
            numeric = _number(value)
            out[key] = value if numeric is None and value not in (None, "") else numeric
        else:
            out[key] = value
    return out


def _deduplicate_rows(rows: list[dict]) -> list[dict]:
    """ลบ overlay area ที่ซ้ำแบบ payload เดียวกันหลังแยกเป็น strike แล้ว."""
    by_strike: dict[Any, list[dict]] = {}
    for row in rows:
        by_strike.setdefault(row.get("strike"), []).append(row)
    result: list[dict] = []
    for grouped in by_strike.values():
        unique: list[dict] = []
        for row in grouped:
            # coords/template_id describe the overlay geometry, not a second
            # market record; ignore them when comparing duplicate payloads.
            identity = {k: v for k, v in row.items() if k not in {"coords", "template_id"}}
            if not any(
                identity == {k: v for k, v in existing.items() if k not in {"coords", "template_id"}}
                for existing in unique
            ):
                unique.append(row)
        result.extend(unique)
    return sorted(result, key=lambda row: row.get("strike"))


def _normalise_range(item: dict) -> dict:
    fields = dict(item or {})
    out = dict(fields)
    for key in ("lower", "upper", "lowerPercent", "upperPercent", "vol"):
        if key in out:
            value = str(out[key]).replace("%", "")
            numeric = _number(value)
            out[key] = numeric if numeric is not None else out[key]
    return out


def _extract_dte(*texts: str | None) -> tuple[float | None, bool]:
    for text in texts:
        if not text:
            continue
        match = DTE_PATTERN_STRICT.search(text)
        if match:
            return float(match.group(1).replace(",", "")), False
    for text in texts:
        if not text:
            continue
        match = DTE_PATTERN_LOOSE.search(text)
        if match:
            return float(match.group(1).replace(",", "")), True
    return None, False


def _extract_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text or "", re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _marker_number(marker_text: str, label: str) -> float | None:
    return _extract_float(rf"{label}\s*:\s*({_NUM})", marker_text)


def _build_series(rows: list[dict], ranges: list[dict]) -> list[dict]:
    """สร้าง series ที่ analyze.py รุ่นเดิมใช้ได้ และยังเก็บ metric ใหม่ใน raw_rows."""
    def series(name: str, field: str) -> dict:
        return {
            "name": name,
            "data": [
                {"x": row.get("strike"), "y": row.get(field), "category": row.get("strike")}
                for row in rows
                if row.get("strike") is not None and row.get(field) is not None
            ],
        }

    result = [
        series("Put", "ivolumePut"),
        series("Call", "ivolumeCall"),
        series("Put Volume", "volumePut"),
        series("Call Volume", "volumeCall"),
        series("Put OI", "oiPut"),
        series("Call OI", "oiCall"),
        series("Vol Settle", "vol"),
        series("Gamma", "gamma"),
        series("Vega", "vega"),
        series("Theta", "theta"),
    ]
    result.append({
        "name": "Ranges",
        "data": [
            {"x": item.get("title"), "y": item.get("upper"), "lower": item.get("lower")}
            for item in ranges
        ],
    })
    return result


def _parse_intraday(raw: dict) -> dict:
    chart = raw.get("chart_data") or {}
    rows = [_normalise_row(item) for item in chart.get("strike_rows", [])]
    rows = [row for row in rows if row.get("strike") is not None]
    rows = _deduplicate_rows(rows)
    if not rows:
        raise ParseError("พบ image-map แต่ไม่มี strike row ที่มีข้อมูล fields")

    ranges_by_title: dict[str, dict] = {}
    for item in chart.get("expected_ranges", []):
        normalised = _normalise_range(item)
        title = normalised.get("title")
        if title:
            ranges_by_title[title] = normalised
    ranges = list(ranges_by_title.values())

    heading = raw.get("page_heading") or chart.get("heading") or ""
    page_text = raw.get("page_text") or ""
    dte, dte_low_confidence = _extract_dte(heading, page_text)
    expiration_selection = raw.get("expiration_selection") or {}
    selector_dte = expiration_selection.get("dte_hint")
    if isinstance(selector_dte, (int, float)) and selector_dte > 0:
        # The selector exposes fractional time-to-expiry (e.g. 2.45), while
        # the chart heading rounds it down to an integer (e.g. 2 DTE).
        dte = float(selector_dte)
        dte_low_confidence = False

    contract = heading.strip() or None
    if contract:
        contract = re.sub(r"\s+", " ", contract)

    future_price = None
    future_chg = None
    future_markers = chart.get("future_markers") or []
    for marker in future_markers:
        marker_text = str(marker)
        if re.search(r"Settle\s*:", marker_text, re.IGNORECASE):
            future_price = _marker_number(marker_text, "Future")
            break
    if future_price is None and future_markers:
        future_price = _marker_number(str(future_markers[0]), "Future")
    if future_price is None:
        future_price = _extract_float(r"\bvs\s*(%s)" % _NUM, heading)

    atm_vol = _extract_float(r"at\s*(%s)\s*%%\s*Volatility" % _NUM, heading)
    if atm_vol is None and rows:
        # The image-map's per-strike `vol` is the available fallback.
        vols = [row["vol"] for row in rows if isinstance(row.get("vol"), (int, float))]
        atm_vol = sum(vols) / len(vols) if vols else None

    # Intraday Volume is the explicit metric in the QuikStrike tooltip. Keep
    # regular Volume separately inside raw_series for callers that need it.
    put_volume = sum(
        row.get("ivolumePut") or 0 for row in rows
        if isinstance(row.get("ivolumePut"), (int, float))
    )
    call_volume = sum(
        row.get("ivolumeCall") or 0 for row in rows
        if isinstance(row.get("ivolumeCall"), (int, float))
    )
    put_regular_volume = sum(
        row.get("volumePut") or 0 for row in rows
        if isinstance(row.get("volumePut"), (int, float))
    )
    call_regular_volume = sum(
        row.get("volumeCall") or 0 for row in rows
        if isinstance(row.get("volumeCall"), (int, float))
    )

    delta_levels: dict[str, float] = {}
    for marker in chart.get("delta_markers") or []:
        delta = marker.get("delta")
        strike = _number(marker.get("strike"))
        if delta and strike is not None:
            delta_levels[str(delta)] = strike

    raw_series = {
        "mode": "intraday",
        "expiration_selection": expiration_selection,
        "object_id": chart.get("object_id"),
        "chart_image_url": chart.get("chart_image_url"),
        "chart_image_width": chart.get("chart_image_width"),
        "chart_image_height": chart.get("chart_image_height"),
        "heading": heading,
        "future_markers": future_markers,
        "delta_markers": chart.get("delta_markers") or [],
        "expected_ranges": ranges,
        "strike_rows": rows,
        "totals": {
            "intraday_volume_put": put_volume,
            "intraday_volume_call": call_volume,
            "intraday_volume_total": put_volume + call_volume,
            "regular_volume_put": put_regular_volume,
            "regular_volume_call": call_regular_volume,
            "regular_volume_total": put_regular_volume + call_regular_volume,
            "open_interest_put": sum(row.get("oiPut") or 0 for row in rows),
            "open_interest_call": sum(row.get("oiCall") or 0 for row in rows),
            "open_interest_total": sum(row.get("oiTotal") or 0 for row in rows),
        },
        "series": _build_series(rows, ranges),
    }

    return {
        "contract": contract,
        "dte": dte,
        "dte_low_confidence": dte_low_confidence,
        "future_price": future_price,
        "future_chg": future_chg,
        "put_volume": int(put_volume),
        "call_volume": int(call_volume),
        "vol": atm_vol,
        "vol_chg": None,
        "delta_levels": delta_levels,
        "raw_series": raw_series,
        "screenshot": raw.get("screenshot"),
    }


def _parse_legacy(raw: dict) -> dict:
    """รองรับ raw จาก scraper รุ่นเดิมที่ยังคืน Highcharts charts เป็น list."""
    if not raw.get("charts"):
        raise ParseError("raw data ไม่มี charts หรือ intraday strike rows")
    chart = raw["charts"][0]
    subtitle = chart.get("subtitle") or ""
    future_price = None
    delta_levels = {}
    for line in chart.get("plotLines", []):
        label = line.get("label") or ""
        if label.startswith("Future:"):
            future_price = line.get("value")
        elif label:
            delta_levels[label] = line.get("value")
    dte, low_conf = _extract_dte(
        raw.get("page_text"), raw.get("page_heading"), subtitle, chart.get("title")
    )
    def get(pattern: str) -> float | None:
        return _extract_float(pattern, subtitle)
    put = get(r"Put:.*?>\s*(%s)" % _NUM)
    call = get(r"Call:.*?>\s*(%s)" % _NUM)
    if future_price is None or put is None or call is None:
        raise ParseError("ดึงค่า legacy ไม่ครบ future/put/call")
    return {
        "contract": chart.get("title"), "dte": dte, "dte_low_confidence": low_conf,
        "future_price": future_price, "future_chg": get(r"Future Chg:.*?>\s*(%s)" % _NUM),
        "put_volume": int(put), "call_volume": int(call),
        "vol": get(r"(?<!Chg)Vol:.*?>\s*(%s)" % _NUM),
        "vol_chg": get(r"Vol Chg:.*?>\s*(%s)" % _NUM),
        "delta_levels": delta_levels, "raw_series": chart.get("series", []),
        "screenshot": raw.get("screenshot"),
    }


def parse(raw: dict) -> dict:
    if raw.get("chart_data", {}).get("strike_rows"):
        return _parse_intraday(raw)
    return _parse_legacy(raw)


if __name__ == "__main__":
    import json
    from scraper import scrape

    parsed = parse(scrape())
    debug = {**parsed, "screenshot": f"<{len(parsed['screenshot'])} bytes>" if parsed.get("screenshot") else None}
    print(json.dumps(debug, ensure_ascii=False, indent=2))
