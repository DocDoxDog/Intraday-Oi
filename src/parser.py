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
    vols=[r["vol"] for r in rows if isinstance(r.get("vol"),(int,float))]
    raw_series={"mode":"open_interest","expiration_selection":sel,"heading":heading,"strike_rows":rows,"oi_positioning_rows":rows,"totals":{"open_interest_view_put":sum(r.get("oiPut") or 0 for r in rows),"open_interest_view_call":sum(r.get("oiCall") or 0 for r in rows),"open_interest_view_total":sum(r.get("oiTotal") or 0 for r in rows),"open_interest_put":sum(r.get("oiPut") or 0 for r in rows),"open_interest_call":sum(r.get("oiCall") or 0 for r in rows),"open_interest_total":sum(r.get("oiTotal") or 0 for r in rows)},"series":_build_series(rows,[])}
    chart_png=None
    try:
        from oi_chart import render_oi_positioning
        chart_png=render_oi_positioning(rows,title=heading or "Gold")
    except Exception: pass
    return {"contract":heading,"dte":dte,"dte_low_confidence":low,"future_price":future,"future_chg":None,"put_volume":0,"call_volume":0,"vol":sum(vols)/len(vols) if vols else None,"vol_chg":None,"delta_levels":{},"raw_series":raw_series,"screenshot":chart_png or raw.get("screenshot")}

def _parse_legacy(raw):
    chart=(raw.get("chart_data") or {}).get("charts",[])
    if not chart: raise ParseError("ไม่พบ Open Interest chart")
    c=chart[0]; series={s.get("name",""):s.get("data",[]) for s in c.get("series",[])}
    puts={p.get("x"):p.get("y") for p in series.get("Put",[])}; calls={p.get("x"):p.get("y") for p in series.get("Call",[])}
    rows=[{"strike":x,"oiPut":puts.get(x,0),"oiCall":calls.get(x,0),"oiTotal":(puts.get(x,0) or 0)+(calls.get(x,0) or 0)} for x in sorted(set(puts)|set(calls))]
    heading=raw.get("page_heading") or c.get("title") or ""
    future=next((p.get("value") for p in c.get("plotLines",[]) if str(p.get("label","")).startswith("Future:")),None)
    dte,low=_extract_dte(heading,raw.get("page_text"))
    raw_series={"mode":"open_interest","heading":heading,"strike_rows":rows,"oi_positioning_rows":rows,"totals":{"open_interest_view_put":sum(r["oiPut"] or 0 for r in rows),"open_interest_view_call":sum(r["oiCall"] or 0 for r in rows),"open_interest_view_total":sum(r["oiTotal"] or 0 for r in rows),"open_interest_put":sum(r["oiPut"] or 0 for r in rows),"open_interest_call":sum(r["oiCall"] or 0 for r in rows),"open_interest_total":sum(r["oiTotal"] or 0 for r in rows)},"series":[{"name":"Put OI","data":[{"x":r["strike"],"y":r["oiPut"]} for r in rows]},{"name":"Call OI","data":[{"x":r["strike"],"y":r["oiCall"]} for r in rows]}]}
    chart_png=None
    try:
        from oi_chart import render_oi_positioning
        chart_png=render_oi_positioning(rows,title=heading or "Gold")
    except Exception: pass
    return {"contract":heading,"dte":dte,"dte_low_confidence":low,"future_price":future,"future_chg":None,"put_volume":0,"call_volume":0,"vol":None,"vol_chg":None,"delta_levels":{},"raw_series":raw_series,"screenshot":chart_png or raw.get("screenshot")}

def parse(raw):
    if (raw.get("chart_data") or {}).get("strike_rows"): return _parse_image_map(raw)
    return _parse_legacy(raw)

if __name__ == "__main__":
    import json
    from scraper import scrape
    p=parse(scrape()); print(json.dumps({**p,"screenshot":f"<{len(p['screenshot'])} bytes>" if p.get('screenshot') else None},ensure_ascii=False,indent=2))
