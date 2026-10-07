"""Deterministic market-regime gate."""
from __future__ import annotations
from typing import Any

def _trend(state: dict[str,Any], tf:str)->str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("trend") or "").lower()

def build_market_regime(state: dict[str,Any]) -> dict[str,Any]:
    technical = state.get("technical") or {}
    news = state.get("news") or []
    fresh_high = [
        x for x in news
        if str(x.get("freshness") or "").upper() in {"FRESH","RECENT"}
        and str(x.get("relevance") or "").upper() in {"HIGH","CRITICAL"}
    ]
    h4,h1,m15,m5 = (_trend(state,x) for x in ("h4","h1","m15","m5"))
    auction = state.get("auction") or {}
    cfd = ((state.get("price") or {}).get("cfd"))
    poc = auction.get("poc")
    bin_size = auction.get("bin_size")
    near_value = (
        isinstance(cfd,(int,float)) and isinstance(poc,(int,float))
        and isinstance(bin_size,(int,float)) and abs(cfd-poc) <= bin_size*2
    )
    aligned = h4 in {"bullish","bearish"} and h4 == h1
    directional_m15 = aligned and m15 == h4

    if fresh_high:
        regime, gate, bias, reason = (
            "EVENT", "WAIT", "MIXED", "Fresh high-relevance catalyst is active."
        )
    elif directional_m15:
        regime, gate, bias, reason = (
            "TREND", "CONTINUATION", h4.upper(),
            "H4/H1 and M15 structure are directionally aligned."
        )
    elif near_value and (m15 in {"neutral",""} or not aligned):
        regime, gate, bias, reason = (
            "BALANCE", "MEAN_REVERSION_ALLOWED", "MIXED",
            "Price is near profile value and directional structure is not fully aligned."
        )
    elif (h4 and h1 and h4 != h1) or (m15 in {"bullish","bearish"} and not aligned):
        regime, gate, bias, reason = (
            "TRANSITION", "REVERSAL_OR_WAIT", "MIXED",
            "Higher-timeframe structure is conflicting or transitioning."
        )
    else:
        regime, gate, bias, reason = (
            "TRANSITION", "WAIT", "MIXED",
            "Structure is insufficient for a clean regime."
        )

    return {
        "version":"regime-v2",
        "regime":regime,
        "bias":bias,
        "gate":gate,
        "reason":reason,
        "catalyst_count":len(fresh_high),
        "timeframes":{"h4":h4,"h1":h1,"m15":m15,"m5":m5},
    }
