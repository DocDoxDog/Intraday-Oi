"""Point-in-time multi-timeframe market memory from persisted OHLC bars."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from .supabase_client import get_client

ALIASES={"1H":["1h","h1","1H"],"4H":["4h","h4","4H"],"1D":["1d","d1","D1"],"1W":["1w","w1","W1"],"1M":["1mo","1m","mo1","1M"]}

def _f(v:Any)->float|None:
    try:return None if v is None else float(v)
    except(TypeError,ValueError):return None

def _summary(rows:list[dict[str,Any]])->dict[str,Any]:
    rows=sorted(rows,key=lambda x:str(x.get("bar_time") or ""))
    if not rows:return {"status":"NO_DATA","bars":0}
    closes=[_f(x.get("close")) for x in rows]; closes=[x for x in closes if x is not None]
    highs=[_f(x.get("high")) for x in rows]; highs=[x for x in highs if x is not None]
    lows=[_f(x.get("low")) for x in rows]; lows=[x for x in lows if x is not None]
    first=closes[0] if closes else None; last=closes[-1] if closes else None
    ret=(last/first-1.0) if first not in (None,0) and last is not None else None
    return {"status":"VALID","bars":len(rows),"first_time":rows[0].get("bar_time"),"last_time":rows[-1].get("bar_time"),"first_close":first,"last_close":last,"return":ret,"high":max(highs) if highs else None,"low":min(lows) if lows else None}

def load_multi_timeframe_memory(instrument:str="XAU/USD",limit:int=500)->dict[str,Any]:
    client=get_client(); out={"version":"historical-memory-v1","instrument":instrument,"as_of":datetime.now(timezone.utc).isoformat(),"horizons":{}}
    for horizon,aliases in ALIASES.items():
        rows=[]
        for tf in aliases:
            try:
                result=(client.table("market_bars").select("bar_time,open,high,low,close,volume,timeframe").eq("source","twelve_data").eq("instrument",instrument).eq("timeframe",tf).order("bar_time",desc=True).limit(limit).execute())
                rows=result.data or []
                if rows: break
            except Exception:
                continue
        out["horizons"][horizon]=_summary(rows)
    return out
__all__=["load_multi_timeframe_memory"]