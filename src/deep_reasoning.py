"""Deep cross-domain reasoning context for the Gold analyst."""
from __future__ import annotations
from typing import Any
def _d(v: Any) -> Any:
    if isinstance(v,(int,float,str,bool)) or v is None:return v
    if isinstance(v,dict):return {str(k):_d(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [_d(x) for x in v]
    return str(v)
def _pick(d: dict[str,Any], *keys:str)->dict[str,Any]:
    return {k:d.get(k) for k in keys if k in d}
def build_deep_reasoning_context(parsed:dict[str,Any], history:dict[str,Any]|None=None)->dict[str,Any]:
    raw=parsed.get("raw_series") or {}; state=raw.get("market_state") or {}; decision=state.get("decision") or {}
    gamma=raw.get("gex") or {}; totals=raw.get("totals") or {}; technical=parsed.get("technical_context") or {}
    volatility=state.get("volatility") or {}; macro=raw.get("macro_state") or {}; flow=raw.get("market_flow") or {}
    multi=raw.get("multi_expiry_gamma") or {}; zones=raw.get("multi_expiry_gamma_zones") or {}
    return _d({
      "as_of":parsed.get("observed_at") or parsed.get("retrieved_at"),
      "market":{"product":parsed.get("product_symbol"),"contract":parsed.get("contract"),"cfd":parsed.get("cfd_price"),"futures":parsed.get("future_price"),"spot":parsed.get("spot_price"),"basis":parsed.get("basis_diff",parsed.get("basis")),"future_change":parsed.get("future_chg")},
      "structure":{"regime":state.get("regime") or {},"decision":decision,"path":state.get("path") or flow.get("path") or {},"levels":state.get("levels") or {},"market_flow":_pick(flow,"status","market_read","flow_read","nodes","path"),"price_memory":flow.get("price_memory") or state.get("price_memory") or {}},
      "technical":technical,
      "options":{"totals":totals,"gex":_pick(gamma,"status","net_gex","call_gex_total","put_gex_total","gamma_flip","call_wall","put_wall","max_abs_gex_strike","gex_unit","gamma_source"),"multi_expiry":{"status":multi.get("status"),"expiration_count":multi.get("expiration_count"),"columns":multi.get("columns") or [],"zones":zones,"totals":multi.get("totals") or {}},"oi_intelligence":{"delta_exposure":raw.get("delta_exposure") or {},"flow_hypotheses":raw.get("flow_hypotheses") or {},"oi_migration":raw.get("oi_migration") or {},"history_comparison":raw.get("history_comparison") or {}}},
      "volatility":{"current_iv":parsed.get("vol",parsed.get("iv")),"iv_change":parsed.get("vol_chg"),**volatility},
      "quant":raw.get("quant_metrics") or parsed.get("quant_metrics") or {},
      "macro":macro,"news":parsed.get("news_context") or {},"history":history or {},
      "historical_memory":raw.get("historical_memory") or raw.get("multi_timeframe_memory") or {},
      "conflicts":decision.get("conflicts") or [],
      "data_quality":{"analysis_status":state.get("analysis_status"),"evidence_completeness":state.get("evidence_completeness"),"limitations":parsed.get("data_limitations") or []}
    })
__all__=["build_deep_reasoning_context"]