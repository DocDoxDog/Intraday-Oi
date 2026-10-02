"""
parser.py
=========
แปลง raw dict จาก scraper.py เป็น schema ของ options_flow_snapshots
พร้อมรองรับ Open Interest View จาก QuikStrike free tier
"""

from __future__ import annotations
import re
from typing import Any

class ParseError(Exception):
    pass

_NUM = r"-?[\d,]+(?:\.\d+)?"
DTE_PATTERN_STRICT = re.compile(rf"\(({_NUM})\s*DTE\)\s*vs\s*{_NUM}", re.I)
DTE_PATTERN_LOOSE = re.compile(rf"\(({_NUM})\s*DTE\)", re.I)
_INT_FIELDS = {"oiCall","oiPut","oiTotal","volumeCall","volumePut","volumeTotal","ivolumeCall","ivolumePut","ivolumeTotal"}
_FLOAT_FIELDS = {"callPremium","putPremium","straddlePremium","callSettle","putSettle","straddleSettle","callChange","putChange","straddleChange","vol","callDelta","putDelta","gamma","vega","theta","oichgvCall","oichgvPut","oichgvTotal"}
_CHANGE_FIELDS = {"oiCallChange","oiPutChange","oiTotalChange","volumeCallChange","volumePutChange","volumeTotalChange"}

def _number(value: Any) -> float | int | None:
    if value is None: return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"no change","n/a","na","null","none"}: return None
    try: number = float(text)
    except ValueError: return None
    return int(number) if number.is_integer() else number

def _iv_percent(value: Any) -> float | int | None:
    number = _number(value)
    if isinstance(number, (int, float)) and abs(number) <= 2:
        number *= 100
    return number

def _extract_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text or "", re.I)
    return float(match.group(1).replace(",", "")) if match else None

def _extract_dte(*texts: str | None) -> tuple[float | None, bool]:
    for text in texts:
        if text:
            m = DTE_PATTERN_STRICT.search(text)
            if m: return float(m.group(1).replace(",", "")), False
    for text in texts:
        if text:
            m = DTE_PATTERN_LOOSE.search(text)
            if m: return float(m.group(1).replace(",", "")), True
    return None, False

def _product_symbol(text: str) -> str | None:
    match = re.search(r"\b(GC|SI|CL|ES|NQ)\b", text or "", re.I)
    return match.group(1).upper() if match else None

def _marker_number(text: str, label: str) -> float | None:
    return _extract_float(rf"{label}\s*:\s*({_NUM})", text)

def _normalise_row(row: dict) -> dict:
    fields = dict(row.get("fields") or {})
    title = fields.get("title") or ""
    m = re.search(rf"({_NUM})\s*Strike", title, re.I)
    out = {"strike": _number(m.group(1)) if m else None, "coords": row.get("coords"), "template_id": row.get("template_id")}
    for key, value in fields.items():
        if key in _INT_FIELDS: out[key] = _number(value)
        elif key in _FLOAT_FIELDS or key in _CHANGE_FIELDS:
            n = _number(value); out[key] = value if n is None and value not in (None, "") else n
        else: out[key] = value
    return out

def _deduplicate_rows(rows):
    out = {}
    for row in rows:
        key = row.get("strike")
        identity = {k:v for k,v in row.items() if k not in {"coords","template_id"}}
        out.setdefault(key, {})
        out[key].setdefault(str(identity), row)
    return sorted([v for group in out.values() for v in group.values()], key=lambda r: r.get("strike") or 0)

def _build_series(rows, ranges):
    def series(name, field):
        return {"name":name,"data":[{"x":r.get("strike"),"y":r.get(field),"category":r.get("strike")} for r in rows if r.get("strike") is not None and r.get(field) is not None]}
    return [series("Put OI","oiPut"),series("Call OI","oiCall"),series("Put OI Change","oiPutChange"),series("Call OI Change","oiCallChange"),series("Vol Settle","vol")]

def _secondary_maps(raw):
    maps = {}
    for view_name, payload in (raw.get("secondary_views") or {}).items():
        charts = (payload or {}).get("charts") or []
        if not charts:
            continue
        series = {s.get("name"): s.get("data") or [] for s in charts[0].get("series", [])}
        maps[view_name] = {
            name: {point.get("x"): point.get("y") for point in points}
            for name, points in series.items()
        }
    return maps

def _attach_gex(parsed: dict) -> dict:
    """คำนวณ GEX จาก gamma/OI จริงที่ QuikStrike ส่งมา โดยไม่สร้าง Greeks เอง."""
    try:
        try:
            from .gex import enrich_raw_series
        except ImportError:
            from gex import enrich_raw_series
        parsed["raw_series"] = enrich_raw_series(
            parsed.get("raw_series") or {}, parsed.get("future_price")
        )
    except Exception as exc:
        parsed.setdefault("raw_series", {})["gex"] = {
            "status": "error",
            "reason": str(exc),
        }
    return parsed


def _aux_value(fields: dict[str, Any], *, side: str, kind: str) -> float | int | None:
    """Find a source value whose key explicitly names side + change/churn."""
    candidates = []
    for key, value in (fields or {}).items():
        key_text = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if kind == "change":
            if not re.search(r"change|chg|oichg|oichange", key_text) or "churn" in key_text:
                continue
        elif kind == "churn":
            if "churn" not in key_text:
                continue
        else:
            continue
        if side not in key_text:
            continue
        number = _number(value)
        if number is not None:
            candidates.append(number)
    return candidates[0] if candidates else None


def _merge_secondary_views(rows: list[dict], secondary_views: dict) -> tuple[list[dict], dict]:
    """Attach OI Change / Churn source observations; missing remains UNKNOWN."""
    by_strike = {row.get("strike"): row for row in rows if row.get("strike") is not None}
    totals = {
        "oi_change_put": None,
        "oi_change_call": None,
        "oi_change_total": None,
        "quikstrike_churn_put": None,
        "quikstrike_churn_call": None,
        "churn": None,
    }

    for view_name, payload in (secondary_views or {}).items():
        if not isinstance(payload, dict):
            continue

        aux_rows = payload.get("rows") or []
        if aux_rows:
            for aux in aux_rows:
                if not isinstance(aux, dict):
                    continue
                strike = _number(aux.get("strike"))
                if strike is None:
                    continue
                target = by_strike.get(strike)
                if target is None:
                    continue
                fields = aux.get("fields") or {}
                if view_name == "oi_change":
                    put_change = _aux_value(fields, side="put", kind="change")
                    call_change = _aux_value(fields, side="call", kind="change")
                    if put_change is not None:
                        target["oiPutChange"] = put_change
                    if call_change is not None:
                        target["oiCallChange"] = call_change
                elif view_name == "churn":
                    put_churn = _aux_value(fields, side="put", kind="churn")
                    call_churn = _aux_value(fields, side="call", kind="churn")
                    if put_churn is not None:
                        target["churnPut"] = put_churn
                    if call_churn is not None:
                        target["churnCall"] = call_churn

        charts = payload.get("charts") or []
        if charts:
            for series in charts[0].get("series", []):
                name = str(series.get("name") or "").lower()
                side = "put" if "put" in name else "call" if "call" in name else None
                if not side:
                    continue
                if view_name == "oi_change":
                    target_key = "oiPutChange" if side == "put" else "oiCallChange"
                elif view_name == "churn":
                    target_key = "churnPut" if side == "put" else "churnCall"
                else:
                    continue
                for point in series.get("data") or []:
                    strike = _number(point.get("x"))
                    value = _number(point.get("y"))
                    if strike is not None and value is not None and strike in by_strike:
                        by_strike[strike][target_key] = value

    def summed(key: str):
        values = [row.get(key) for row in rows if isinstance(row.get(key), (int, float))]
        return sum(values) if values else None

    totals["oi_change_put"] = summed("oiPutChange")
    totals["oi_change_call"] = summed("oiCallChange")
    if totals["oi_change_put"] is not None or totals["oi_change_call"] is not None:
        totals["oi_change_total"] = sum(
            value for value in (totals["oi_change_put"], totals["oi_change_call"])
            if isinstance(value, (int, float))
        )

    totals["quikstrike_churn_put"] = summed("churnPut")
    totals["quikstrike_churn_call"] = summed("churnCall")
    if totals["quikstrike_churn_put"] is not None or totals["quikstrike_churn_call"] is not None:
        totals["churn"] = sum(
            value for value in (totals["quikstrike_churn_put"], totals["quikstrike_churn_call"])
            if isinstance(value, (int, float))
        )
    return rows, totals


def _parse_image_map(raw):
    chart = raw.get("chart_data") or {}; rows = _deduplicate_rows([_normalise_row(x) for x in chart.get("strike_rows",[])])
    if not rows: raise ParseError("ไม่พบ OI strike rows")
    heading = raw.get("page_heading") or chart.get("heading") or ""
    dte, low = _extract_dte(heading, raw.get("page_text")); sel=raw.get("expiration_selection") or {}
    if isinstance(sel.get("dte_hint"),(int,float)): dte=float(sel["dte_hint"]); low=False
    future=None
    for marker in chart.get("future_markers") or []:
        future=_marker_number(str(marker),"Future")
        if future is not None: break
    future = future or _extract_float(r"\bvs\s*(%s)"%_NUM,heading)
    vols=[_iv_percent(r["vol"]) for r in rows if isinstance(r.get("vol"),(int,float))]
    secondary_views = raw.get("secondary_views") or {}
    rows, secondary_totals = _merge_secondary_views(rows, secondary_views)
    def _sum_optional(field: str) -> int | float | None:
        values = [r.get(field) for r in rows if isinstance(r.get(field), (int, float))]
        return sum(values) if values else None

    oi_totals = {
        "open_interest_view_put": sum(r.get("oiPut") or 0 for r in rows),
        "open_interest_view_call": sum(r.get("oiCall") or 0 for r in rows),
        "open_interest_view_total": sum(r.get("oiTotal") or 0 for r in rows),
        "open_interest_put": sum(r.get("oiPut") or 0 for r in rows),
        "open_interest_call": sum(r.get("oiCall") or 0 for r in rows),
        "open_interest_total": sum(r.get("oiTotal") or 0 for r in rows),
        "volume_put": _sum_optional("volumePut"),
        "volume_call": _sum_optional("volumeCall"),
        "intraday_volume_put": _sum_optional("ivolumePut"),
        "intraday_volume_call": _sum_optional("ivolumeCall"),
        **secondary_totals,
    }
    raw_series={"mode":"open_interest","dte":dte,"expiration_selection":sel,"heading":heading,"strike_rows":rows,"oi_positioning_rows":rows,"expected_ranges":chart.get("expected_ranges") or [],"secondary_views":list(secondary_views),"totals":oi_totals,"series":_build_series(rows,[])}
    # IMPORTANT: screenshot means the actual QuikStrike source image.
    # Never replace it with a locally rendered OI chart. The old implementation
    # did exactly that, so Telegram labeled a synthetic chart as "Source Screenshot".
    parsed = {
        "contract": heading,
        "product_symbol": _product_symbol(heading),
        "expiration_code": sel.get("selected"),
        "dte": dte,
        "dte_low_confidence": low,
        "future_price": future,
        "future_chg": None,
        "put_volume": oi_totals.get("volume_put"),
        "call_volume": oi_totals.get("volume_call"),
        "vol": sum(vols) / len(vols) if vols else None,
        "vol_chg": None,
        "delta_levels": {},
        "raw_series": raw_series,
        "screenshot": raw.get("source_screenshot") or raw.get("screenshot"),
    }
    return _attach_gex(parsed)

def _parse_legacy(raw):
    chart=(raw.get("chart_data") or {}).get("charts",[])
    if not chart: raise ParseError("ไม่พบ Open Interest chart")
    c=chart[0]; series={s.get("name",""):s.get("data",[]) for s in c.get("series",[])}
    puts={p.get("x"):p.get("y") for p in series.get("Put",[])}; calls={p.get("x"):p.get("y") for p in series.get("Call",[])}
    secondary = _secondary_maps(raw)
    oi_change = secondary.get("oi_change", {})
    churn = secondary.get("churn", {})
    vol_map = {p.get("x"): p.get("y") for p in series.get("Vol Settle", [])}
    put_changes = oi_change.get("Put", {})
    call_changes = oi_change.get("Call", {})
    rows=[]
    for x in sorted(set(puts)|set(calls)):
        row={"strike":x,"oiPut":puts.get(x,0),"oiCall":calls.get(x,0),"oiTotal":(puts.get(x,0) or 0)+(calls.get(x,0) or 0)}
        if x in put_changes: row["oiPutChange"] = put_changes[x]
        if x in call_changes: row["oiCallChange"] = call_changes[x]
        if x in vol_map: row["vol"] = _iv_percent(vol_map[x])
        churn_put = churn.get("Put", {}).get(x)
        churn_call = churn.get("Call", {}).get(x)
        if churn_put is not None: row["churnPut"] = churn_put
        if churn_call is not None: row["churnCall"] = churn_call
        rows.append(row)
    heading=raw.get("page_heading") or c.get("title") or ""
    future=next((p.get("value") for p in c.get("plotLines",[]) if str(p.get("label","")).startswith("Future:")),None)
    dte,low=_extract_dte(heading,raw.get("page_text"))
    totals={"open_interest_view_put":sum(r["oiPut"] or 0 for r in rows),"open_interest_view_call":sum(r["oiCall"] or 0 for r in rows),"open_interest_view_total":sum(r["oiTotal"] or 0 for r in rows),"open_interest_put":sum(r["oiPut"] or 0 for r in rows),"open_interest_call":sum(r["oiCall"] or 0 for r in rows),"open_interest_total":sum(r["oiTotal"] or 0 for r in rows),"oi_change_put":sum(r.get("oiPutChange") or 0 for r in rows),"oi_change_call":sum(r.get("oiCallChange") or 0 for r in rows),"quikstrike_churn_put":sum(r.get("churnPut") or 0 for r in rows),"quikstrike_churn_call":sum(r.get("churnCall") or 0 for r in rows)}
    raw_series={"mode":"open_interest","dte":dte,"heading":heading,"strike_rows":rows,"oi_positioning_rows":rows,"expected_ranges":c.get("expected_ranges") or [],"secondary_views":list(secondary),"totals":totals,"series":[{"name":"Put OI","data":[{"x":r["strike"],"y":r["oiPut"]} for r in rows]},{"name":"Call OI","data":[{"x":r["strike"],"y":r["oiCall"]} for r in rows]},{"name":"Put OI Change","data":[{"x":r["strike"],"y":r.get("oiPutChange")} for r in rows if r.get("oiPutChange") is not None]},{"name":"Call OI Change","data":[{"x":r["strike"],"y":r.get("oiCallChange")} for r in rows if r.get("oiCallChange") is not None]},{"name":"Vol Settle","data":[{"x":r["strike"],"y":r.get("vol")} for r in rows if r.get("vol") is not None]}]}
    iv_values = [r.get("vol") for r in rows if isinstance(r.get("vol"), (int, float))]
    parsed = {
        "contract": heading,
        "product_symbol": _product_symbol(heading),
        "expiration_code": (raw.get("expiration_selection") or {}).get("selected"),
        "dte": dte,
        "dte_low_confidence": low,
        "future_price": future,
        "future_chg": None,
        "put_volume": sum(r.get("volumePut") or 0 for r in rows) if any(isinstance(r.get("volumePut"), (int, float)) for r in rows) else None,
        "call_volume": sum(r.get("volumeCall") or 0 for r in rows) if any(isinstance(r.get("volumeCall"), (int, float)) for r in rows) else None,
        "vol": sum(iv_values) / len(iv_values) if iv_values else None,
        "vol_chg": None,
        "delta_levels": {},
        "raw_series": raw_series,
        "screenshot": raw.get("source_screenshot") or raw.get("screenshot"),
    }
    return _attach_gex(parsed)

def parse(raw):
    if raw.get("expiration_snapshots"):
        snapshots = []
        for item in raw["expiration_snapshots"]:
            parsed_item = parse(item)
            parsed_item.pop("screenshot", None)
            snapshots.append(parsed_item)
        primary_raw = {k: v for k, v in raw.items() if k != "expiration_snapshots"}
        primary = parse(primary_raw)
        primary["expiration_snapshots"] = snapshots
        primary["multi_expiration"] = {
            "enabled": True,
            "count": len(snapshots),
            "codes": [item.get("expiration_code") for item in snapshots],
        }
        return primary
    if (raw.get("chart_data") or {}).get("strike_rows"): return _parse_image_map(raw)
    return _parse_legacy(raw)

if __name__ == "__main__":
    import json
    from scraper import scrape
    p=parse(scrape()); print(json.dumps({**p,"screenshot":f"<{len(p['screenshot'])} bytes>" if p.get('screenshot') else None},ensure_ascii=False,indent=2))
