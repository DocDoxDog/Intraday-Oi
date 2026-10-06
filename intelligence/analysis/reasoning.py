"""Build an evidence-first Analyst V3 scaffold without inventing market facts."""
from __future__ import annotations
import hashlib, json
from typing import Any
from .regime import assess_regime
from .conflict import detect_conflicts

def _id(prefix,payload):
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()[:10]
    return f"{prefix}_{digest}"

def build_analysis(*, product:str, as_of:str, market_state:dict[str,Any], evidence:dict[str,Any]) -> dict[str,Any]:
    facts=[]
    for ref,item in evidence.items():
        if not isinstance(item,dict): continue
        domain=str(item.get("domain") or item.get("type") or "UNKNOWN").upper()
        statement=item.get("statement") or item.get("label")
        if statement:
            facts.append({"id":_id("F",{"ref":ref,"statement":statement}),"domain":domain,"statement":str(statement),"evidence_refs":[str(ref)],"confidence":1.0})
    regime=assess_regime(market_state)
    conflicts=detect_conflicts(facts=facts)
    uncertainty=[]
    if regime.state=="UNKNOWN": uncertainty.append("Regime cannot be established from deterministic evidence.")
    if conflicts: uncertainty.append("Conflicting evidence requires conditional scenarios.")
    return {
      "analysis_id":_id("ANL",{"product":product,"as_of":as_of,"evidence":sorted(evidence)}),
      "as_of":as_of,"product":product,
      "regime":{"state":regime.state,"confidence":regime.confidence,"evidence_refs":list(regime.evidence_refs),"limitations":list(regime.limitations)},
      "facts":facts,"interpretations":[],"conflicts":conflicts,"scenarios":[],
      "trade_plan":{"state":"WAIT","long":{},"short":{}},
      "why_not_long":[],"why_not_short":[],"uncertainties":uncertainty,"narrative":{}
    }
