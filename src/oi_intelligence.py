"""Deterministic OI exposure, flow hypotheses and migration analysis."""
from __future__ import annotations
from typing import Any
def _f(v:Any,d=None):
    try:return float(v)
    except (TypeError,ValueError):return d
def classify_flow(row,price_change=None,iv_change=None):
    dc=_f(row.get("oi_delta_call")); dp=_f(row.get("oi_delta_put")); evidence=[]
    if dc is not None:
        if dc>0:evidence.append("call_oi_increase")
        elif dc<0:evidence.append("call_oi_decrease")
    if dp is not None:
        if dp>0:evidence.append("put_oi_increase")
        elif dp<0:evidence.append("put_oi_decrease")
    if price_change is not None:evidence.append("underlying_price_change")
    if iv_change is not None:evidence.append("iv_change")
    label="UNKNOWN"; confidence=0.0
    if dc is None or dp is None:
        return {"label":"UNKNOWN","confidence":0.0,"evidence":evidence,"limitations":["OI baseline unavailable; ΔOI is unknown","OI change alone does not identify aggressor side"]}
    if price_change is not None and dc>0 and price_change>0: label,confidence="NEW_LONG",0.35
    elif price_change is not None and dc<0 and price_change>0: label,confidence="SHORT_COVER",0.35
    elif price_change is not None and dp>0 and price_change<0: label,confidence="NEW_LONG",0.30
    elif price_change is not None and dp<0 and price_change<0: label,confidence="LONG_LIQUIDATION",0.30
    return {"label":label,"confidence":confidence,"evidence":evidence,"limitations":["OI change alone does not identify aggressor side","volume/bid-ask/option price are required for stronger flow classification"]}
def delta_adjusted_exposure(rows,multiplier=100.0):
    out=[]; net=0.0; gross=0.0
    for r in rows:
        if not isinstance(r, dict):
            out.append({"call_delta_exposure":None,"put_delta_exposure":None,"net_delta_exposure":None,"gross_delta_exposure":None,"delta_exposure_status":"UNKNOWN"})
            continue
        co=_f(r.get("oiCall")); po=_f(r.get("oiPut")); cd=_f(r.get("callDelta")); pd=_f(r.get("putDelta"))
        if co is None or po is None or cd is None or pd is None:
            x=dict(r)
            x.update({"call_delta_exposure":None,"put_delta_exposure":None,"net_delta_exposure":None,"gross_delta_exposure":None,"delta_exposure_status":"UNKNOWN"})
            out.append(x)
            continue
        ce=co*cd*multiplier; pe=po*pd*multiplier; ne=ce+pe
        net+=ne; gross+=abs(ce)+abs(pe); x=dict(r)
        x.update({"call_delta_exposure":ce,"put_delta_exposure":pe,"net_delta_exposure":ne,"gross_delta_exposure":abs(ce)+abs(pe),"delta_exposure_status":"VALID"}); out.append(x)
    valid_rows=[x for x in out if x.get("delta_exposure_status")=="VALID"]
    status="VALID" if len(valid_rows)==len(out) and out else "PARTIAL" if valid_rows else "UNKNOWN"
    return {"contract_multiplier":multiplier,"net_delta_exposure":net if valid_rows else None,"gross_delta_exposure":gross if valid_rows else None,"status":status,"rows":out}
def build_flow_hypotheses(rows,future_change=None):
    events=[]
    for r in rows:
        if not isinstance(r, dict):
            continue
        f=classify_flow(r,future_change)
        if f["label"]!="UNKNOWN" or r.get("oi_delta_call") or r.get("oi_delta_put"):
            events.append({"strike":r.get("strike"),"call_oi":r.get("oiCall"),"put_oi":r.get("oiPut"),"delta_oi_call":r.get("oi_delta_call"),"delta_oi_put":r.get("oi_delta_put"),**f})
    return {"events":events,"unknown_rate":sum(e["label"]=="UNKNOWN" for e in events)/len(events) if events else 1.0}
def oi_migration(previous_rows,current_rows):
    prev={float(r["strike"]):r for r in (previous_rows or []) if isinstance(r, dict) and r.get("strike") is not None}; cur={float(r["strike"]):r for r in (current_rows or []) if isinstance(r, dict) and r.get("strike") is not None}; shifts=[]
    for side,field in (("call","oiCall"),("put","oiPut")):
        known_prev = {k: _f(v.get(field)) for k, v in prev.items() if _f(v.get(field)) is not None}
        known_cur = {k: _f(v.get(field)) for k, v in cur.items() if _f(v.get(field)) is not None}
        common = set(known_prev) & set(known_cur)
        dec=sorted([(k, known_prev[k]-known_cur[k]) for k in common if known_prev[k] > known_cur[k]], key=lambda x:x[1], reverse=True)
        inc=sorted([(k, known_cur[k]-known_prev[k]) for k in common if known_cur[k] > known_prev[k]], key=lambda x:x[1], reverse=True)
        for fs,amt in dec[:10]:
            if inc:
                ts,target=min(inc,key=lambda x:abs(x[0]-fs)); qty=min(amt,target)
                if qty>0:shifts.append({"side":side,"from_strike":fs,"to_strike":ts,"estimated_oi":qty})
    return {"shifts":shifts,"method":"nearest-strike OI redistribution hypothesis","confidence":"low_without_trade_volume"}
def enrich(current,previous=None):
    # History/parse payloads can legitimately contain null JSON objects.
    # Never let a missing raw_series turn deterministic intelligence into a
    # NoneType exception; preserve UNKNOWN instead.
    if not isinstance(current, dict):
        raise TypeError("OI_INTELLIGENCE_CURRENT_MUST_BE_DICT")
    raw = current.get("raw_series")
    if not isinstance(raw, dict):
        raw = {}
        current["raw_series"] = raw
    rows = raw.get("oi_positioning_rows")
    if not isinstance(rows, list):
        rows = raw.get("strike_rows")
    if not isinstance(rows, list):
        rows = []
    raw["delta_exposure"]=delta_adjusted_exposure(rows)
    raw["flow_hypotheses"]=build_flow_hypotheses(rows,current.get("future_chg"))
    previous_raw = previous.get("raw_series") if isinstance(previous, dict) else {}
    if not isinstance(previous_raw, dict):
        previous_raw = {}
    pr = previous_raw.get("oi_positioning_rows")
    if not isinstance(pr, list):
        pr = previous_raw.get("strike_rows")
    if not isinstance(pr, list):
        pr = []
    raw["oi_migration"] = oi_migration(pr, rows)
    previous_obj = previous if isinstance(previous, dict) else {}
    
    def side_total(items, field):
        vals=[_f(r.get(field)) for r in items if _f(r.get(field)) is not None]
        return sum(vals) if vals else None
    
    current_put=side_total(rows,"oiPut")
    current_call=side_total(rows,"oiCall")
    previous_put=side_total(pr,"oiPut")
    previous_call=side_total(pr,"oiCall")
    raw["history_delta_1h"] = {
        "status": "VALID" if previous_put is not None and previous_call is not None else "UNKNOWN",
        "oi_put": current_put - previous_put if current_put is not None and previous_put is not None else None,
        "oi_call": current_call - previous_call if current_call is not None and previous_call is not None else None,
        "oi_total": (
            (current_put + current_call) - (previous_put + previous_call)
            if current_put is not None and current_call is not None and previous_put is not None and previous_call is not None
            else None
        ),
        "churn": (
            abs(current_put - previous_put) + abs(current_call - previous_call)
            if current_put is not None and current_call is not None and previous_put is not None and previous_call is not None
            else None
        ),
        "future_price_change": (
            _f(current.get("future_price")) - _f(previous_obj.get("future_price"))
            if _f(current.get("future_price")) is not None and _f(previous_obj.get("future_price")) is not None
            else None
        ),
        "vol_change": (
            _f(current.get("vol")) - _f(previous_obj.get("vol"))
            if _f(current.get("vol")) is not None and _f(previous_obj.get("vol")) is not None
            else None
        ),
        "gex_change": (
            _f((raw.get("gex") or {}).get("net_gex")) - _f(((previous_obj.get("raw_series") or {}).get("gex") or {}).get("net_gex"))
            if _f((raw.get("gex") or {}).get("net_gex")) is not None and _f(((previous or {}).get("raw_series") or {}).get("gex", {}).get("net_gex")) is not None
            else None
        ),
    }
    raw["intelligence_version"]="oi-intelligence-v2"; return current
