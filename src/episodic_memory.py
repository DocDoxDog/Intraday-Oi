"""V6 point-in-time episodic memory. Outcomes are quarantined from production retrieval."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
from datetime import datetime, timezone

VERSION="episodic-memory-v6.0"

def _parse(x):
    if not x: return None
    try:
        return datetime.fromisoformat(str(x).replace("Z","+00:00"))
    except ValueError: return None

def _eligible(asof, episode):
    a=_parse(asof); e=_parse(episode.get("information_time") or episode.get("asof"))
    return bool(a and e and e <= a)

def _similar(a,b):
    keys=("trend","volatility","gamma","auction","liquidity","flow","event","location")
    return sum(1 for k in keys if a.get(k)==b.get(k))

@dataclass(frozen=True)
class Episode:
    episode_id: str
    information_time: str
    fingerprint: dict[str,Any]
    evidence_snapshot: dict[str,Any]
    outcome: dict[str,Any] | None = None
    provenance: tuple[str,...]=()
    def to_dict(self):
        d=asdict(self); d["provenance"]=list(self.provenance); return d

def retrieve_episodes(current: dict[str,Any], episodes: list[dict[str,Any]], limit: int=5) -> list[dict[str,Any]]:
    asof=current.get("asof") or current.get("information_time")
    ranked=[]
    for ep in episodes or []:
        if not _eligible(asof,ep): continue
        fp=ep.get("fingerprint") or {}
        score=_similar(current.get("fingerprint") or {},fp)
        ranked.append((score,ep))
    ranked.sort(key=lambda x:(x[0],x[1].get("information_time","")),reverse=True)
    out=[]
    for score,ep in ranked[:max(0,limit)]:
        # Production gets evidence only; historical outcomes are never injected into current evidence.
        out.append({"episode_id":ep.get("episode_id"),"information_time":ep.get("information_time"),
                    "similarity":score,"fingerprint":ep.get("fingerprint") or {},
                    "evidence_snapshot":ep.get("evidence_snapshot") or {},
                    "outcome_available_for_research":bool(ep.get("outcome"))})
    return out

def build_memory_context(state: dict[str,Any], episodes: list[dict[str,Any]]|None=None) -> dict[str,Any]:
    fp=state.get("regime_fingerprint") or {}
    return {"version":VERSION,"asof":state.get("observed_at") or state.get("retrieved_at"),
            "fingerprint":fp,"episodes":retrieve_episodes({"asof":state.get("observed_at") or state.get("retrieved_at"),"fingerprint":fp},episodes or [],5),
            "guardrails":["information_time must be <= decision asof","future outcomes never become current evidence","research labels remain quarantined"]}
