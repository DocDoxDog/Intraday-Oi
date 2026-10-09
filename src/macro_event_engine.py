"""Point-in-time macro/news normalization.

Actual/Forecast/Previous are accepted only when supplied by the source. No
numeric release values are inferred. Surprise and transmission are derived
deterministically from validated source values.
"""
from __future__ import annotations
from typing import Any

def _n(v: Any) -> float | None:
    try: return None if v in (None,"") else float(v)
    except (TypeError,ValueError): return None

def normalize_release(event: dict[str,Any], *, as_of: str | None=None) -> dict[str,Any]:
    actual=_n(event.get("actual")); forecast=_n(event.get("forecast")); previous=_n(event.get("previous"))
    status="VALID" if actual is not None else "PENDING"
    out={"event_id":event.get("id") or event.get("event_id"),
         "name":event.get("name") or event.get("title"),
         "release_time":event.get("release_time") or event.get("observed_at"),
         "actual":actual,"forecast":forecast,"previous":previous,
         "status":status,"evidence_refs":event.get("evidence_refs") or []}
    if actual is not None and forecast is not None:
        out["surprise_raw"]=round(actual-forecast,8)
        out["surprise_direction"]="ABOVE_FORECAST" if actual>forecast else "BELOW_FORECAST" if actual<forecast else "AT_FORECAST"
    else:
        out["surprise_raw"]=None; out["surprise_direction"]="UNKNOWN"
    return out

def gold_transmission(release: dict[str,Any]) -> dict[str,Any]:
    """Map only broad validated economic direction; never invent market response."""
    name=str(release.get("name") or "").lower()
    surprise=release.get("surprise_direction")
    if surprise=="UNKNOWN": return {"stance":"UNKNOWN","chain":[],"market_response":"UNKNOWN"}
    # Directional mapping is a hypothesis, not an observed response.
    inflation=any(k in name for k in ("cpi","pce","inflation","core price"))
    labor=any(k in name for k in ("nfp","payroll","employment","jobless","unemployment"))
    rates=any(k in name for k in ("fed","fomc","rate","interest"))
    if inflation or labor or rates:
        stance="GOLD_NEGATIVE_IF_ABOVE_FORECAST" if surprise=="ABOVE_FORECAST" else "GOLD_POSITIVE_IF_BELOW_FORECAST" if surprise=="BELOW_FORECAST" else "NEUTRAL"
        return {"stance":stance,"chain":["macro surprise","Fed expectations","US yields / USD","Gold"],"market_response":"OBSERVE_PRICE_RESPONSE"}
    return {"stance":"UNKNOWN","chain":["macro release","cross-asset response","Gold"],"market_response":"OBSERVE_PRICE_RESPONSE"}
