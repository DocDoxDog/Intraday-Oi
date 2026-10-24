"""V6 deterministic regime fingerprint: point-in-time, explainable, no future labels."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
import hashlib, json

VERSION = "regime-fingerprint-v6.0"

def _num(x):
    try:
        if x is None or isinstance(x, bool) or x == "": return None
        return float(x)
    except (TypeError, ValueError): return None

def _up(x): return str(x or "").strip().upper()

@dataclass(frozen=True)
class RegimeFingerprint:
    version: str
    asof: str
    trend: str
    volatility: str
    gamma: str
    auction: str
    liquidity: str
    flow: str
    narrative: str
    event: str
    location: str
    fingerprint_id: str
    provenance: tuple[str, ...] = ()

    def to_dict(self):
        d=asdict(self); d["provenance"]=list(self.provenance); return d

def _trend(ms):
    t=ms.get("technical") or {}
    h4=_up((t.get("h4") or {}).get("trend")); h1=_up((t.get("h1") or {}).get("trend"))
    if h4 in {"BULLISH","BEARISH"} and h4==h1: return h4
    if h4 in {"BULLISH","BEARISH"}: return "MIXED"
    if h1 in {"BULLISH","BEARISH"}: return h1
    return "UNKNOWN"

def build_regime_fingerprint(state: dict[str,Any]) -> dict[str,Any]:
    raw=state.get("raw_series") or {}; ms=raw.get("market_state") or {}
    vol=ms.get("volatility") or {}; gamma=ms.get("gamma") or {}; auction=ms.get("auction") or {}
    flow=ms.get("order_flow") or {}; crowd=next((raw.get(k) for k in ("narrative_intelligence","social_intelligence","youtube_intelligence") if raw.get(k)),None)
    news=ms.get("news") or []
    gex=_num(gamma.get("net_gex"))
    gamma_state="POSITIVE_GAMMA" if gex is not None and gex>0 else "NEGATIVE_GAMMA" if gex is not None and gex<0 else "UNKNOWN"
    iv=_num(vol.get("iv"))
    vol_state="UNKNOWN" if iv is None else "HIGH" if iv>=25 else "ELEVATED" if iv>=20 else "NORMAL"
    loc=str((auction.get("location") or "UNKNOWN")).upper()
    auction_state=str(auction.get("state") or auction.get("mode") or ("OUTSIDE_VALUE" if loc in {"ABOVE_VALUE","BELOW_VALUE"} else "VALUE")).upper()
    ag=(flow.get("aggression") or {})
    delta=_num(ag.get("delta"))
    flow_state="BUY_AGGRESSION" if delta is not None and delta>0 else "SELL_AGGRESSION" if delta is not None and delta<0 else "UNKNOWN"
    liq="UNKNOWN"
    spread=_num(flow.get("spread"))
    if spread is not None: liq="WIDE" if spread>1 else "NORMAL"
    narrative=_up((crowd or {}).get("direction") if isinstance(crowd,dict) else None) or "UNKNOWN"
    event="FRESH_HIGH_RELEVANCE" if any(isinstance(x,dict) and _up(x.get("freshness")) in {"FRESH","RECENT"} and _up(x.get("relevance")) in {"HIGH","CRITICAL"} for x in news) else "NORMAL"
    payload={"trend":_trend(ms),"volatility":vol_state,"gamma":gamma_state,"auction":auction_state,"liquidity":liq,"flow":flow_state,"narrative":narrative,"event":event,"location":loc}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:16]
    return RegimeFingerprint(VERSION,str(state.get("observed_at") or state.get("retrieved_at") or ""),**payload,fingerprint_id=digest,
      provenance=("market_state.technical","market_state.volatility","market_state.gamma","market_state.auction","market_state.order_flow","market_state.news")).to_dict()
