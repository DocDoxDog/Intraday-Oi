"""Deterministic market-regime gate."""
from __future__ import annotations
from typing import Any

def _trend(state: dict[str,Any], tf:str)->str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("trend") or "").lower()

def build_market_regime(state: dict[str,Any]) -> dict[str,Any]:
    technical=state.get("technical") or {}
    news=state.get("news") or []
    fresh_high=[x for x in news if str(x.get("freshness") or "").upper() in {"FRESH","RECENT"}
                and str(x.get("relevance") or "").upper() in {"HIGH","CRITICAL"}]
    h4,h1,m15,m5=(_trend(state,x) for x in ("h4","h1","m15","m5"))
    auction=state.get("auction") or {}
    cfd=((state.get("price") or {}).get("cfd"))
    near_value=False
    poc=auction.get("poc")
    if isinstance(cfd,(int,float)) and isinstance(poc,(int,float)) and auction.get("bin_size"):
        near_value=abs(cfd-poc) <= auction["bin_size"]*2
    if fresh_high:
        regime="EVENT"; gate="WAIT"; bias="MIXED"; reason="Fresh high-relevance catalyst is active."
    elif h4 in {"bullish","bearish"} and h4==h1==m15:
        regime="TREND"; gate="CONTINUATION"; bias=h4.upper(); reason="Higher-timeframe and M15 structure are aligned."
    elif h4=="mixed" or h1 in {"bullish","bearish"} and h4!=h1:
        regime="TRANSITION"; gate="REVERSAL_OR_WAIT"; bias="MIXED"; reason="Higher-timeframe structure is changing or conflicting."
    elif near_value and m15 in {"neutral",""}:
        regime="BALANCE"; gate="MEAN_REVERSION_ALLOWED"; bias="MIXED"; reason="Price is near profile value with limited directional structure."
    else:
        regime="TRANSITION"; gate="WAIT"; bias="MIXED"; reason="Structure is insufficient for a clean regime."
    return {"version":"regime-v1","regime":regime,"bias":bias,"gate":gate,
            "reason":reason,"catalyst_count":len(fresh_high)}
