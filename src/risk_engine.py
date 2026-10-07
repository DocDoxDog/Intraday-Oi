"""Deterministic setup risk and transaction-cost gate."""
from __future__ import annotations
from typing import Any
import os

def _n(v:Any)->float|None:
    try: return None if v in (None,"") else float(v)
    except (TypeError,ValueError): return None

def evaluate_setup_risk(side:str, entry:float|None, stop:float|None,
                        targets:list[float|None], *,
                        atr:float|None=None, spread:float|None=None,
                        slippage:float|None=None,
                        min_rr:float|None=None, max_stop_atr:float|None=None)->dict[str,Any]:
    min_rr = float(os.environ.get("MIN_RR1","1.0")) if min_rr is None else min_rr
    max_stop_atr = float(os.environ.get("MAX_STOP_ATR_MULTIPLE","3.0")) if max_stop_atr is None else max_stop_atr
    e,s=_n(entry),_n(stop)
    is_long=str(side).upper().startswith("LONG")
    if e is None or s is None: return {"status":"NO_TRADE","reason":"MISSING_ENTRY_OR_STOP"}
    risk=e-s if is_long else s-e
    if risk<=0: return {"status":"NO_TRADE","reason":"INVALID_STOP_DIRECTION"}
    gross=[]
    for tp in targets:
        t=_n(tp)
        if t is None: continue
        reward=t-e if is_long else e-t
        gross.append(round(reward/risk,2) if reward>0 else None)
    rr1=gross[0] if gross else None
    if rr1 is None: return {"status":"NO_TRADE","reason":"NO_QUALIFIED_TP1","risk_distance":round(risk,5),"rr":[]}
    if rr1 < min_rr: return {"status":"NO_TRADE","reason":"RR_BELOW_MIN","risk_distance":round(risk,5),"rr":gross,"rr1":rr1}
    if atr is not None and atr>0 and risk>max_stop_atr*atr:
        return {"status":"NO_TRADE","reason":"STOP_TOO_FAR","risk_distance":round(risk,5),
                "atr":atr,"max_stop_atr_multiple":max_stop_atr,"rr":gross}
    cost=None
    if spread is not None or slippage is not None:
        cost=max(0.0,_n(spread) or 0.0)+max(0.0,_n(slippage) or 0.0)
    rr_cost=[]
    for i,tp in enumerate(targets):
        r=gross[i] if i<len(gross) else None
        if r is None or cost is None: rr_cost.append(None); continue
        reward=((_n(tp)-e) if is_long else (e-_n(tp)))
        rr_cost.append(round(max(0.0,reward-cost)/(risk+cost),2))
    return {"status":"PASS","reason":"RISK_QUALIFIED","risk_distance":round(risk,5),
            "rr":gross,"rr1":rr1,"cost_per_roundtrip":cost,"cost_adjusted_rr":rr_cost,
            "max_stop_atr_multiple":max_stop_atr}
