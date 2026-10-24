"""Immutable trade-plan journal helpers."""
from __future__ import annotations
import uuid
from datetime import datetime,timezone
from typing import Any
def _num(v:Any)->float|None:
    if v in (None,"") or isinstance(v,bool): return None
    try:return float(v)
    except(TypeError,ValueError):return None
def _route_rows(ai:dict[str,Any])->list[dict[str,Any]]:
    ex=((ai.get("trade_plan") or {}).get("execution_plan") or {})
    if not isinstance(ex,dict):return []
    routes=ex.get("routes")
    if not isinstance(routes,list):routes=[ex.get(k) for k in ("long_reclaim","long_support","short_rejection","short_breakdown")]
    out=[]
    for r in routes:
        if not isinstance(r,dict):continue
        entry=_num(r.get("entry",r.get("trigger"))); stop=_num(r.get("stop")); targets=[_num(x) for x in (r.get("targets") or [])]; targets=[x for x in targets if x is not None]
        state=str(r.get("state") or "").upper()
        if entry is None or stop is None or not targets or state in {"NO_TRADE","WAIT","DATA_INSUFFICIENT","INVALIDATED"}:continue
        out.append({"route":r.get("route") or r.get("title") or r.get("strategy"),"side":r.get("side"),"state":state,"entry":entry,"stop":stop,"targets":targets,"confidence":r.get("confidence"),"risk":r.get("risk") or {},"evidence_refs":r.get("evidence_refs") or []})
    return out
def build_plan_journal_rows(parsed:dict[str,Any],ai:dict[str,Any],snapshot_id:int|None=None)->list[dict[str,Any]]:
    run_id=ai.get("llm_run_id") or (ai.get("_llm_telemetry") or {}).get("run_id") or str(uuid.uuid4())
    state=(parsed.get("raw_series") or {}).get("market_state") or {}; decision=state.get("decision") or {}
    base={"snapshot_id":snapshot_id,"run_id":str(run_id),"instrument":parsed.get("product_symbol") or parsed.get("contract") or "GOLD","as_of":parsed.get("observed_at") or parsed.get("retrieved_at"),"cfd_price":parsed.get("cfd_price"),"futures_price":parsed.get("future_price"),"market_bias":decision.get("structural_bias") or ai.get("bias"),"market_regime":decision.get("decision_state") or state.get("regime"),"analysis_status":ai.get("analysis_status"),"evidence_snapshot":{"decision":decision,"market_state":state,"gex":(parsed.get("raw_series") or {}).get("gex") or {},"totals":(parsed.get("raw_series") or {}).get("totals") or {},"technical":parsed.get("technical_context") or {},"macro":(parsed.get("raw_series") or {}).get("macro_state") or {},"historical_memory":(parsed.get("raw_series") or {}).get("historical_memory") or {}}}
    return [{**base,"plan_id":str(uuid.uuid4()),**r,"status":"OPEN"} for r in _route_rows(ai)]
def persist_trade_plan_journal(client:Any,parsed:dict[str,Any],ai:dict[str,Any],snapshot_id:int|None=None)->int:
    rows=build_plan_journal_rows(parsed,ai,snapshot_id)
    if not rows:return 0
    result=client.table("trade_plan_journal").insert(rows).execute()
    return len(result.data or rows)
def mark_plan_outcome(client:Any,plan_id:str,outcome:dict[str,Any])->None:
    payload={"status":outcome.get("status","CLOSED"),"entry_hit_at":outcome.get("entry_hit_at"),"sl_hit_at":outcome.get("sl_hit_at"),"tp1_hit_at":outcome.get("tp1_hit_at"),"tp2_hit_at":outcome.get("tp2_hit_at"),"tp3_hit_at":outcome.get("tp3_hit_at"),"mfe":_num(outcome.get("mfe")),"mae":_num(outcome.get("mae")),"outcome_snapshot":outcome.get("outcome_snapshot") or {},"evaluated_at":datetime.now(timezone.utc).isoformat()}
    client.table("trade_plan_journal").update(payload).eq("plan_id",plan_id).execute()
__all__=["build_plan_journal_rows","persist_trade_plan_journal","mark_plan_outcome"]