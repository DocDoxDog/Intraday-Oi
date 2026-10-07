"""Action-zone semantics built from deterministic market context."""
from __future__ import annotations
from typing import Any

STATES={"WAIT","APPROACHING","IN_ZONE","TRIGGERED","CONFIRMED","INVALIDATED","NO_TRADE"}

def _n(v:Any)->float|None:
    try: return None if v in (None,"") else float(v)
    except (TypeError,ValueError): return None

def _trend(state,tf): return str(((state.get("technical") or {}).get(tf) or {}).get("trend") or "").lower()
def _bos(state,tf): return str(((state.get("technical") or {}).get(tf) or {}).get("bos") or "").lower()

def _zone_state(current,zone,tolerance,triggered,invalidated=False):
    if zone is None: return "WAIT"
    if invalidated: return "INVALIDATED"
    if triggered: return "TRIGGERED"
    if current is None: return "WAIT"
    d=abs(current-zone)
    if d <= tolerance: return "IN_ZONE"
    # One tolerance-band outside is approaching; beyond that is WAIT.
    if d <= tolerance*3: return "APPROACHING"
    return "WAIT"

def _setup(name,side,zone,state,action,event,invalidation,evidence=None,limitations=None):
    return {"setup_type":name,"side":side,"zone_price":zone,"state":state,"action":action,
            "event_required":event,"invalidation":invalidation,
            "evidence":evidence or [],"limitations":limitations or []}

def build_action_zones(market_state:dict[str,Any])->dict[str,Any]:
    price=market_state.get("price") or {}
    current=_n(price.get("cfd"))
    levels=market_state.get("levels") or {}
    regime=market_state.get("regime") or {}
    auction=market_state.get("auction") or {}
    flow=market_state.get("order_flow") or {}
    long_trigger=_n(market_state.get("market_map",{}).get("long_trigger") or levels.get("resistance_current"))
    short_trigger=_n(market_state.get("market_map",{}).get("short_trigger") or levels.get("support_current"))
    support=_n(market_state.get("market_map",{}).get("long_support_trigger"))
    tol=_n((market_state.get("technical") or {}).get("m5",{}).get("atr14")) or _n(auction.get("bin_size")) or 1.0
    tol=max(tol*0.25,0.5)
    m15,m5=_trend(market_state,"m15"),_trend(market_state,"m5")
    m5bos=_bos(market_state,"m5")
    htf=str(regime.get("bias") or "MIXED").upper()
    flow_hyp=[x.get("type") for x in flow.get("hypotheses") or [] if isinstance(x,dict)]
    flow_note="flow evidence supplied" if flow.get("status")=="OK" else "order-flow evidence unavailable"
    long_break_state=_zone_state(current,long_trigger,tol,current is not None and long_trigger is not None and current>long_trigger)
    short_break_state=_zone_state(current,short_trigger,tol,current is not None and short_trigger is not None and current<short_trigger)
    support_state=_zone_state(current,support,tol,current is not None and support is not None and current<=(support+tol))
    setups={}
    setups["pullback_long"]=_setup("PULLBACK","LONG",long_trigger,
        long_break_state if htf=="BULLISH" else "WAIT","buy continuation",
        "retest + reaction + bullish structure",
        "loss of continuation structure",[f"HTF={htf}",f"M15={m15}",f"M5={m5}",flow_note])
    setups["pullback_short"]=_setup("PULLBACK","SHORT",short_trigger,
        short_break_state if htf=="BEARISH" else "WAIT","sell continuation",
        "retest + rejection + bearish structure",
        "reclaim of failed breakdown structure",[f"HTF={htf}",f"M15={m15}",f"M5={m5}",flow_note])
    setups["breakout_retest_long"]=_setup("BREAKOUT_RETEST","LONG",long_trigger,
        "IN_ZONE" if long_break_state=="IN_ZONE" else long_break_state,
        "break → accept → retest → continue",
        "breakout + acceptance above + retest hold","return below breakout structure",
        [f"M15={m15}",f"M5={m5}",flow_note])
    setups["breakout_retest_short"]=_setup("BREAKOUT_RETEST","SHORT",short_trigger,
        "IN_ZONE" if short_break_state=="IN_ZONE" else short_break_state,
        "break → accept → retest → continue",
        "breakdown + acceptance below + retest failure","reclaim above breakdown structure",
        [f"M15={m15}",f"M5={m5}",flow_note])
    reversal_long_state=_zone_state(current,support,tol,False)
    if current is not None and support is not None and current<=support+tol and m5bos in {"bullish","bull","up","bos_up","bullish_bos","break_up"}:
        reversal_long_state="TRIGGERED"
    setups["reversal_long"]=_setup("REVERSAL","LONG",support,reversal_long_state,
        "support → rejection / absorption → structure shift",
        "sell-side liquidity interaction + rejection + bullish BOS",
        "acceptance below support",[f"M5 BOS={m5bos}",flow_note]+flow_hyp)
    reversal_short_state=_zone_state(current,long_trigger,tol,False)
    if current is not None and long_trigger is not None and current>=long_trigger-tol and m5bos in {"bearish","bear","down","bos_down","bearish_bos","break_down"}:
        reversal_short_state="TRIGGERED"
    setups["reversal_short"]=_setup("REVERSAL","SHORT",long_trigger,reversal_short_state,
        "resistance → rejection / absorption → structure shift",
        "buy-side liquidity interaction + rejection + bearish BOS",
        "acceptance above resistance",[f"M5 BOS={m5bos}",flow_note]+flow_hyp)
    return {"version":"action-zone-v1","status":"OK","tolerance":tol,"setups":setups,
            "summary":[x for x in setups.keys() if setups[x]["state"] not in {"WAIT","NO_TRADE"}]}
