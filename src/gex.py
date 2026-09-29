"""GC/Gold options GEX calculation from QuikStrike strike rows."""
from __future__ import annotations
import math
from typing import Any
GC_CONTRACT_MULTIPLIER=100.0
def _num(v:Any)->float|None:
    try:return None if v is None else float(v)
    except(TypeError,ValueError):return None
def _crossing_level(rows,key):
    prev=None
    for row in rows:
        v=_num(row.get(key)); s=_num(row.get("strike"))
        if v is None or s is None: continue
        if prev is not None:
            ps,pv=prev
            if pv==0:return ps
            if (pv<0<=v) or (pv>0>=v):
                return s if v==pv else ps+(s-ps)*(-pv)/(v-pv)
        prev=(s,v)
    return None
def black76_gamma(F,strike,iv_percent,dte_days):
    if F<=0 or strike<=0 or iv_percent is None or dte_days<=0:return None
    sigma=iv_percent/100.0; T=dte_days/365.0
    if sigma<=0:return None
    d1=(math.log(F/strike)+0.5*sigma*sigma*T)/(sigma*math.sqrt(T))
    return math.exp(-0.5*d1*d1)/math.sqrt(2*math.pi)/(F*sigma*math.sqrt(T))
def calculate_gex(rows,future_price,dte_days=None,multiplier=GC_CONTRACT_MULTIPLIER):
    F=_num(future_price)
    if F is None or F<=0:return {"status":"unavailable","reason":"future_price_missing","rows":[]}
    out=[]
    for raw in rows:
        strike=_num(raw.get("strike")); gamma=_num(raw.get("gamma")); source="quikstrike"
        if gamma is None and strike is not None:
            iv=_num(raw.get("vol")); dte=_num(dte_days)
            if iv is not None and dte is not None:
                gamma=black76_gamma(F,strike,iv,dte); source="black76_iv_fallback"
        if strike is None or gamma is None:continue
        call_oi=_num(raw.get("oiCall")) or 0.0; put_oi=_num(raw.get("oiPut")) or 0.0
        scale=multiplier*(F**2)*0.01
        cg=gamma*call_oi*scale; pg=-gamma*put_oi*scale
        x=dict(raw); x.update({"call_gex":cg,"put_gex":pg,"net_gex":cg+pg,"gamma":gamma,"gex_multiplier":multiplier,"gamma_source":source}); out.append(x)
    out.sort(key=lambda r:r["strike"]); cum=0.0
    for r in out: cum+=r["net_gex"]; r["cumulative_gex"]=cum
    net=sum(r["net_gex"] for r in out)
    return {"status":"ok" if out else "unavailable","underlying":"GC","future_price":F,"contract_multiplier":multiplier,"gex_unit":"USD per 1% underlying move","convention":"dealer_call_positive_put_negative","net_gex":net,"call_gex_total":sum(r["call_gex"] for r in out),"put_gex_total":sum(r["put_gex"] for r in out),"call_wall":max(out,key=lambda r:r["call_gex"])["strike"] if out else None,"put_wall":min(out,key=lambda r:r["put_gex"])["strike"] if out else None,"max_abs_gex_strike":max(out,key=lambda r:abs(r["net_gex"]))["strike"] if out else None,"gamma_flip":_crossing_level(out,"cumulative_gex"),"positive_gamma":net>0,"source_gamma_count":sum(r["gamma_source"]=="quikstrike" for r in out),"derived_gamma_count":sum(r["gamma_source"]=="black76_iv_fallback" for r in out),"rows":out}
def enrich_raw_series(raw_series,future_price):
    result=calculate_gex(raw_series.get("strike_rows") or [],future_price,raw_series.get("dte")); raw_series["gex"]=result
    if result.get("status")=="ok":
        by={r["strike"]:r for r in result["rows"]}
        for row in raw_series.get("strike_rows") or []:
            m=by.get(row.get("strike"))
            if m: row.update({k:m[k] for k in ("call_gex","put_gex","net_gex","cumulative_gex","gamma_source")})
    return raw_series
