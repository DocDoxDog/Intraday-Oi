"""V6 orchestration: deterministic regime + memory + research governance metadata."""
from __future__ import annotations
from typing import Any
from src.regime_fingerprint import build_regime_fingerprint
from src.episodic_memory import build_memory_context

VERSION="market-intelligence-v6.0"

def build_v6_intelligence(state: dict[str,Any], episodes: list[dict[str,Any]]|None=None) -> dict[str,Any]:
    fp=build_regime_fingerprint(state)
    enriched=dict(state); enriched["regime_fingerprint"]=fp
    memory=build_memory_context(enriched,episodes)
    return {"version":VERSION,"status":"READY" if fp.get("fingerprint_id") else "DATA_INSUFFICIENT",
            "regime_fingerprint":fp,"memory":memory,
            "research_policy":{"point_in_time":True,"purged_embargoed":True,"oos_required":True,"cost_adjusted":True,"calibration_required":True,"auto_promotion":False},
            "architecture":["RAW","EVIDENCE","RELATIONSHIP","CONFLICT","SCENARIO","REGIME","MEMORY","RESEARCH_GATE","NARRATIVE","VERIFICATION"],
            "execution_authority":"NONE"}
