"""Deterministic multi-domain market intelligence and trade-plan ranking."""
from __future__ import annotations
from math import sqrt
from statistics import mean, pstdev
from typing import Any

def _n(v: Any):
    try:
        return None if v is None or v == "" or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None

def _ohlcv(parsed, tf):
    return list((((parsed.get("technical_context") or {}).get("ohlcv") or {}).get(tf)) or [])

def _z(xs, x):
    if x is None or len(xs) < 20: return None
    s=pstdev(xs)
    return round((x-mean(xs))/s,4) if s else None

def build_quant_evidence(parsed):
    out={"status":"UNKNOWN","timeframes":{}}
    for tf in ("m5","m15","m30","h1","h4","d1"):
        bars=_ohlcv(parsed,tf); closes=[_n(x.get("close")) for x in bars]; closes=[x for x in closes if x is not None]
        if len(closes)<20: continue
        rs=[closes[i]/closes[i-1]-1 for i in range(1,len(closes)) if closes[i-1]]
        trs=[]
        for i in range(max(1,len(bars)-100),len(bars)):
            c,p=bars[i],bars[i-1]
            trs.append(max(c["high"]-c["low"],abs(c["high"]-p["close"]),abs(c["low"]-p["close"])))
        atr=mean(trs[-14:]) if len(trs)>=14 else None
        out["timeframes"][tf]={
            "return_20": round(closes[-1]/closes[-21]-1,6) if len(closes)>=21 else None,
            "return_zscore": _z(rs[-100:],rs[-1] if rs else None),
            "realized_vol_proxy": round(sqrt(mean([x*x for x in rs[-20:]]))*sqrt(252),6) if len(rs)>=20 else None,
            "atr14": round(atr,5) if atr is not None else None,
            "atr_percentile": round(sum(x<=atr for x in trs[-100:])/min(100,len(trs))*100,2) if atr is not None else None,
        }
    out["status"]="AVAILABLE" if out["timeframes"] else "UNKNOWN"
    return out

def _macro(parsed,state):
    source=state.get("macro") or (parsed.get("raw_series") or {}).get("macro_state") or {}
    items=parsed.get("news_context") or []
    high=[x for x in items if isinstance(x,dict) and str(x.get("relevance") or "").upper()=="HIGH"]
    channels=[]
    for x in high:
        for c in x.get("market_channels") or []:
            if c not in channels: channels.append(str(c))
    label=str(source.get("bias") or source.get("gold_bias") or source.get("status") or "").upper()
    regime="GOLD_SUPPORTIVE" if "SUPPORT" in label else "GOLD_HEADWIND" if ("HEADWIND" in label or "BEAR" in label) else (label or "UNKNOWN")
    return {"regime":regime,"high_relevance_events":len(high),"channels":channels,
            "transmission":"rates/real-yield/USD/liquidity matter only when observed price response agrees"}

def _micro(state):
    t=state.get("technical") or {}; events=[]
    for tf in ("d1","h4","h1","m30","m15","m5"):
        x=t.get(tf) or {}
        for k in ("bos","choch","sweep"):
            v=str(x.get(k) or "none")
            if v!="none": events.append(f"{tf}:{k}={v}")
    return {"events":events,"liquidity_events":[x for x in events if ":sweep=" in x],
            "structure_events":[x for x in events if ":bos=" in x or ":choch=" in x],
            "interpretation":"level and event are kept separate; no tick-level aggressor claim without trade/book data"}

def _psych(state):
    f=state.get("flow") or {}; g=state.get("gamma") or {}; t=state.get("technical") or {}; m=[]
    if any(str((t.get(x) or {}).get("sweep") or "none")!="none" for x in ("m5","m15","h1")): m.append("liquidity_sweep")
    if _n(g.get("net_gex")) is not None and _n(g.get("net_gex"))<0: m.append("hedging_can_amplify_breaks")
    if f.get("oi_change_put") is not None or f.get("oi_change_call") is not None: m.append("positioning_activity_without_aggressor_side")
    return {"mechanisms":m,"interpretation":"behavior is inferred from observable liquidity/positioning mechanisms, not emotion"}

def _name(route,t):
    r=str(route.get("route") or ""); m5=t.get("m5") or {}; f=[]
    if m5.get("sweep") not in (None,"none"): f.append("LIQUIDITY_SWEEP")
    if m5.get("choch") not in (None,"none"): f.append("CHoCH")
    if m5.get("bos") not in (None,"none"): f.append("BOS")
    if m5.get("fvg"): f.append("FVG")
    d=m5.get("divergence") or {}
    if d.get("status")=="DETECTED": f.append("DIVERGENCE")
    if "reclaim" in r: n="ICT/SMC Breakout-Reclaim"
    elif "support" in r: n="ICT Liquidity-Sweep Reversal" if "LIQUIDITY_SWEEP" in f else "SMC Support Reversal"
    elif "rejection" in r: n="ICT/SMC Rejection at Liquidity"
    else: n="CRT/SMC Breakdown-Retest"
    return n,f

def rank_trade_candidates(state,execution):
    t=state.get("technical") or {}; d=state.get("decision") or {}; structural=str(d.get("structural_bias") or "MIXED").upper()
    rows=[]
    for r in execution.get("routes") or []:
        if not isinstance(r,dict): continue
        e=_n(r.get("trigger")); s=_n(r.get("stop")); targets=[_n(x) for x in r.get("targets") or [] if _n(x) is not None]
        if e is None or s is None or not targets: continue
        side=str(r.get("side") or "").upper(); score=20; reasons=[]
        aligned=(structural=="BULLISH" and side.startswith("LONG")) or (structural=="BEARISH" and side.startswith("SHORT"))
        if aligned: score+=12; reasons.append("HTF alignment")
        elif structural in ("BULLISH","BEARISH"): score-=8; reasons.append("countertrend")
        for tf,w in (("d1",4),("h4",8),("h1",7),("m15",5),("m5",4)):
            tr=str((t.get(tf) or {}).get("trend") or "").lower()
            if (side.startswith("LONG") and tr=="bullish") or (side.startswith("SHORT") and tr=="bearish"): score+=w
        m5=t.get("m5") or {}; ev=str(m5.get("choch") or "")+" "+str(m5.get("bos") or "")
        if (side.startswith("LONG") and "bullish" in ev) or (side.startswith("SHORT") and "bearish" in ev): score+=8; reasons.append("structure event")
        sw=str(m5.get("sweep") or "")
        if (side.startswith("LONG") and "sell_side" in sw) or (side.startswith("SHORT") and "buy_side" in sw): score+=6; reasons.append("liquidity sweep")
        dv=m5.get("divergence") or {}
        if (side.startswith("LONG") and dv.get("type")=="bullish_regular") or (side.startswith("SHORT") and dv.get("type")=="bearish_regular"): score+=5; reasons.append("divergence")
        if m5.get("fvg") or (t.get("m15") or {}).get("fvg"): score+=3; reasons.append("FVG")
        if (r.get("risk") or {}).get("status")=="PASS": score+=6; reasons.append("risk geometry")
        name,features=_name(r,t)
        rows.append({"route":r.get("route"),"strategy":name,"side":side,"entry":e,"stop":s,"targets":targets[:5],"score":round(score,2),"evidence":reasons,"features":features})
    rows.sort(key=lambda x:(x["score"],len(x["targets"])),reverse=True)
    selected=[]; seen=set()
    for x in rows:
        if x["route"] in seen: continue
        seen.add(x["route"]); x["rank"]=len(selected)+1; selected.append(x)
        if len(selected)==3: break
    return selected

def build_multi_domain_context(parsed,state,execution):
    quant=build_quant_evidence(parsed)
    macro=_macro(parsed,state); micro=_micro(state); psychology=_psych(state)
    candidates=rank_trade_candidates(state,execution)
    conflicts=[]
    structural=str((state.get("decision") or {}).get("structural_bias") or "MIXED").upper()
    for x in candidates:
        if structural=="BULLISH" and x["side"].startswith("SHORT"): conflicts.append("countertrend:"+str(x["route"]))
        if structural=="BEARISH" and x["side"].startswith("LONG"): conflicts.append("countertrend:"+str(x["route"]))
    return {"version":"multi-domain-v1","macro":macro,"microstructure":micro,"psychology":psychology,
            "quant":quant,"strategy_candidates":candidates,"conflicts":conflicts,
            "method":"evidence-first deterministic ranking; score is not probability"}
