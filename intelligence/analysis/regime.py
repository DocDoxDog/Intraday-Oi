"""Deterministic regime assessment from already-derived market evidence."""
from __future__ import annotations
from typing import Any
from .models import RegimeAssessment

def _num(v):
    try: return float(v) if v is not None else None
    except (TypeError, ValueError): return None

def assess_regime(state: dict[str, Any]) -> RegimeAssessment:
    refs=[]; score={"TREND_UP":0,"TREND_DOWN":0,"RANGE":0,"COMPRESSION":0,"EXPANSION":0,"REVERSAL":0,"EVENT_DRIVEN":0,"LIQUIDITY_VACUUM":0}
    technical=state.get("technical") or state.get("technical_analysis") or {}
    tfs=technical.get("timeframes") or {}
    m15=tfs.get("m15") or {}; m5=tfs.get("m5") or {}; h1=tfs.get("h1") or {}
    trends=[x.get("trend") for x in (h1,m15,m5) if x.get("trend")]
    if trends.count("bullish") >= 2: score["TREND_UP"]+=2; refs.append("TECH_TREND_BULLISH")
    if trends.count("bearish") >= 2: score["TREND_DOWN"]+=2; refs.append("TECH_TREND_BEARISH")
    if len(set(trends))>1: score["REVERSAL"]+=1; refs.append("TECH_MIXED")
    for tf in (m15,m5):
        if tf.get("bos") in ("bullish_bos","bearish_bos"): score["EXPANSION"]+=1; refs.append("TECH_BOS")
        if tf.get("sweep") in ("buy_side_sweep","sell_side_sweep"): score["REVERSAL"]+=1; refs.append("TECH_SWEEP")
    atrs=[_num((tfs.get(k) or {}).get("atr14")) for k in ("m15","m5")]
    moms=[_num((tfs.get(k) or {}).get("momentum_pct_5")) for k in ("m15","m5")]
    if all(x is not None for x in atrs) and atrs[0] > 0 and atrs[1] > 0:
        ratio=atrs[1]/atrs[0]
        if ratio < 0.35: score["COMPRESSION"]+=2; refs.append("ATR_COMPRESSION")
        elif ratio > 0.8: score["EXPANSION"]+=1; refs.append("ATR_EXPANSION")
    gex=((state.get("raw_series") or {}).get("gex") or {})
    if gex.get("net_gex") is not None:
        refs.append("GEX_AVAILABLE")
    news=state.get("news") or state.get("news_evidence") or []
    if isinstance(news,list) and news:
        high=[x for x in news if isinstance(x,dict) and str(x.get("importance","")).upper() in {"HIGH","CRITICAL"}]
        if high: score["EVENT_DRIVEN"]+=2; refs.append("HIGH_IMPACT_NEWS")
    best=max(score,key=score.get) if score else "UNKNOWN"
    value=score.get(best,0)
    if value <= 0: return RegimeAssessment("UNKNOWN",0.0,tuple(dict.fromkeys(refs)),("Insufficient deterministic regime evidence",))
    confidence=min(0.95,0.35+0.12*value)
    return RegimeAssessment(best,confidence,tuple(dict.fromkeys(refs)))
