"""Slow Gold macro context from public FRED observations."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import os
import requests

SERIES = {"nominal_10y":"DGS10","real_10y":"DFII10","policy_rate":"DFF","broad_usd":"DTWEXBGS"}

def _num(v: Any) -> float | None:
    try:
        return None if v in (None,"",".") else float(v)
    except (TypeError,ValueError):
        return None

def _direction(cur: float|None, prev: float|None) -> str:
    if cur is None or prev is None: return "UNKNOWN"
    if cur > prev: return "UP"
    if cur < prev: return "DOWN"
    return "FLAT"

def _fetch_series(series: str, api_key: str|None = None) -> dict[str, Any]:
    url = f"https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id":series,"file_type":"json","api_key":api_key or os.environ.get("FRED_API_KEY","")}
    if not params["api_key"]:
        # public CSV is the no-key fallback
        csv_url=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
        resp=requests.get(csv_url,timeout=15)
        resp.raise_for_status()
        lines=resp.text.strip().splitlines()
        rows=[]
        for line in lines[1:]:
            parts=line.split(",")
            if len(parts)>=2 and _num(parts[1]) is not None:
                rows.append({"date":parts[0],"value":parts[1]})
        if len(rows)>=2:
            return {"latest":rows[-1],"previous":rows[-2]}
        return {}
    resp=requests.get(url,params=params,timeout=15)
    resp.raise_for_status()
    obs=[x for x in (resp.json().get("observations") or []) if _num(x.get("value")) is not None]
    if len(obs)>=2:
        return {"latest":obs[-1],"previous":obs[-2]}
    return {}

def build_macro_state(api_key: str|None = None) -> dict[str, Any]:
    state={"version":"macro-state-v1","source":"fred","status":"UNKNOWN",
           "observed_at":datetime.now(timezone.utc).isoformat(),"as_of":None,
           "series":{},"macro_bias":"UNKNOWN","limitations":[]}
    failures=[]
    for name,series in SERIES.items():
        try:
            data=_fetch_series(series,api_key)
            latest,prev=data.get("latest"),data.get("previous")
            cur=_num(latest.get("value")) if latest else None
            old=_num(prev.get("value")) if prev else None
            state["series"][name]={"series_id":series,"value":cur,"previous":old,
                "as_of":latest.get("date") if latest else None,
                "direction":_direction(cur,old)}
            if latest and latest.get("date"): state["as_of"]=max(str(state["as_of"] or ""),str(latest["date"]))
        except Exception as exc:
            failures.append(f"{series}:{type(exc).__name__}")
            state["series"][name]={"series_id":series,"value":None,"previous":None,"as_of":None,"direction":"UNKNOWN"}
    real=state["series"]["real_10y"]["direction"]
    usd=state["series"]["broad_usd"]["direction"]
    if real=="DOWN" and usd=="DOWN": state["macro_bias"]="GOLD_SUPPORTIVE"
    elif real=="UP" and usd=="UP": state["macro_bias"]="GOLD_HEADWIND"
    elif any(state["series"][x]["value"] is not None for x in SERIES): state["macro_bias"]="MIXED"
    if not failures or len(failures)<len(SERIES): state["status"]="OK"
    state["limitations"].append("Macro observations are slow context, not intraday entry signals.")
    state["limitations"].append("Public FRED graph fallback is used when no FRED API key is configured.")
    state["failures"]=failures
    return state
