"""Deterministic market-flow engine: price memory -> structural nodes -> conditional path.

The engine is deliberately LLM-free. It only uses observed prices and source-derived
options levels; it never creates a synthetic price ladder or converts a wick into
a confirmed break.
"""
from __future__ import annotations
from typing import Any

def _n(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None

def _recent_price_path(bars: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    out=[]
    for b in bars[-limit:]:
        c=_n(b.get("close"))
        if c is None: continue
        out.append({"time":b.get("bar_time") or b.get("datetime"),"open":_n(b.get("open")),
                    "high":_n(b.get("high")),"low":_n(b.get("low")),"close":c})
    return out

def build_price_memory(bars_by_tf: dict[str, list[dict[str, Any]]], current_price: float | None = None) -> dict[str, Any]:
    memory={}
    for tf,bars in bars_by_tf.items():
        ordered=sorted([b for b in (bars or []) if isinstance(b,dict)],
                       key=lambda x:str(x.get("bar_time") or x.get("datetime") or ""))
        if not ordered: continue
        window=ordered[-50:]
        highs=[_n(x.get("high")) for x in window if _n(x.get("high")) is not None]
        lows=[_n(x.get("low")) for x in window if _n(x.get("low")) is not None]
        closes=[_n(x.get("close")) for x in ordered if _n(x.get("close")) is not None]
        if not closes: continue
        hi=max(highs) if highs else None; lo=min(lows) if lows else None; last=closes[-1]
        memory[tf]={"last_close":last,"recent_high":hi,"recent_low":lo,
                    "distance_from_high":round(last-hi,5) if hi is not None else None,
                    "distance_from_low":round(last-lo,5) if lo is not None else None,
                    "bars":_recent_price_path(ordered)}
    return {"version":"price-memory-v2","current_price":current_price,"timeframes":memory,
            "status":"VALID" if memory else "UNKNOWN"}

def rank_structural_nodes(price: float, options_nodes=None, technical_nodes=None,
                          price_memory=None, max_nodes: int=12) -> list[dict[str,Any]]:
    raw=(options_nodes or [])+(technical_nodes or [])
    candidates=[]; seen=set()
    for x in raw:
        if not isinstance(x,dict): x={"level":x}
        level=_n(x.get("level",x.get("strike_cfd",x.get("price"))))
        if level is None or level<=0: continue
        key=round(level,5)
        if key in seen: continue
        seen.add(key)
        prominence=_n(x.get("local_prominence"))
        if prominence is None: prominence=_n(x.get("aggregate_gex"))
        if prominence is None: prominence=0.0
        node_type=str(x.get("node_type") or "").upper()
        tier=x.get("tier")
        if tier is None: tier=0 if node_type in {"CALL_WALL","PUT_WALL","GAMMA_FLIP"} else 1
        candidates.append({"level":key,"futures_level":_n(x.get("futures_level")),
                           "source":x.get("source") or "unknown",
                           "role":x.get("role") or x.get("node_type") or "STRUCTURAL_NODE",
                           "tier":int(tier),"direction":"UP" if level>price else "DOWN",
                           "distance_from_price":round(abs(level-price),5),
                           "local_prominence":prominence,"evidence_refs":x.get("evidence_refs") or []})
    # Market path must have a real nearest node on BOTH sides before adding
    # additional continuation nodes. Tier is a ranking aid, not a reason to
    # discard the nearest node on the opposite side.
    up = sorted([x for x in candidates if x["direction"] == "UP"],
                key=lambda x: (x["distance_from_price"], x["tier"], -abs(float(x["local_prominence"]))))
    down = sorted([x for x in candidates if x["direction"] == "DOWN"],
                  key=lambda x: (x["distance_from_price"], x["tier"], -abs(float(x["local_prominence"]))))

    selected=[]
    for side_nodes in (up, down):
        if side_nodes:
            selected.append(side_nodes[0])

    remaining = sorted(
        [x for x in candidates if x not in selected],
        key=lambda x: (x["tier"], x["distance_from_price"], -abs(float(x["local_prominence"])))
    )
    for c in remaining:
        if any(abs(c["level"]-s["level"])<0.01 for s in selected):
            continue
        selected.append(c)
        if len(selected) >= max_nodes:
            break

    return selected[:max_nodes]

def _bar_event(bar: dict[str,Any] | None, level: float, side: str,
               previous: dict[str,Any] | None = None) -> str:
    if not bar: return "NONE"
    close=_n(bar.get("close")); high=_n(bar.get("high")); low=_n(bar.get("low"))
    if close is None: return "NONE"
    tol=max(abs(level)*0.00005,0.05)
    if side=="UP":
        if high is not None and high>=level and close<level-tol: return "REJECT"
        if close>=level+tol: return "BREAK_ACCEPT"
    else:
        if low is not None and low<=level and close>level+tol: return "REJECT"
        if close<=level-tol: return "BREAK_ACCEPT"
    if abs(close-level)<=tol: return "HOLD"
    if previous:
        pc=_n(previous.get("close"))
        if pc is not None:
            if side=="UP" and pc>=level and close<level-tol: return "RECLAIM"
            if side=="DOWN" and pc<=level and close>level+tol: return "RECLAIM"
    return "NONE"

def build_conditional_path(price: float, nodes: list[dict[str,Any]],
                           technical: dict[str,Any] | None=None,
                           recent_bars: list[dict[str,Any]] | None=None) -> dict[str,Any]:
    up=sorted([n for n in nodes if n["level"]>price],key=lambda n:n["level"])
    down=sorted([n for n in nodes if n["level"]<price],key=lambda n:n["level"],reverse=True)
    upper=up[0] if up else None; lower=down[0] if down else None
    next_up=up[1] if len(up)>1 else None; next_down=down[1] if len(down)>1 else None
    last=recent_bars[-1] if recent_bars else None; prev=recent_bars[-2] if recent_bars and len(recent_bars)>1 else None
    transitions=[]
    if upper:
        ev=_bar_event(last,upper["level"],"UP",prev)
        transitions += [
            {"from":"CURRENT","to":upper["level"],"condition_type":"HOLD_REJECT",
             "condition":{"level":upper["level"],"event":"HOLD_OR_REJECT"},"mechanism":"upper structural node","state":"ACTIVE","observed_event":ev},
            {"from":"CURRENT","to":upper["level"],"condition_type":"BREAK_ACCEPT",
             "condition":{"close_above":upper["level"],"acceptance_required":True},"mechanism":"upside continuation","state":"ARMED","observed_event":ev},
        ]
        if next_up: transitions.append({"from":upper["level"],"to":next_up["level"],"condition_type":"BREAK_ACCEPT",
            "condition":{"close_above":next_up["level"],"acceptance_required":True},"mechanism":"next observed node","state":"ARMED"})
    if lower:
        ev=_bar_event(last,lower["level"],"DOWN",prev)
        transitions += [
            {"from":"CURRENT","to":lower["level"],"condition_type":"HOLD_REJECT",
             "condition":{"level":lower["level"],"event":"HOLD_OR_REJECT"},"mechanism":"lower structural node","state":"ACTIVE","observed_event":ev},
            {"from":"CURRENT","to":lower["level"],"condition_type":"BREAK_ACCEPT",
             "condition":{"close_below":lower["level"],"acceptance_required":True},"mechanism":"downside continuation","state":"ARMED","observed_event":ev},
        ]
        if next_down: transitions.append({"from":lower["level"],"to":next_down["level"],"condition_type":"BREAK_ACCEPT",
            "condition":{"close_below":next_down["level"],"acceptance_required":True},"mechanism":"next observed node","state":"ARMED"})
    if lower: transitions.append({"from":lower["level"],"to":"CURRENT","condition_type":"RECLAIM",
        "condition":{"close_above":lower["level"],"reclaim_required":True},"mechanism":"failed downside break","state":"ARMED"})
    if upper: transitions.append({"from":upper["level"],"to":"CURRENT","condition_type":"RECLAIM",
        "condition":{"close_below":upper["level"],"reclaim_required":True},"mechanism":"failed upside break","state":"ARMED"})
    upper_event = _bar_event(last, upper["level"], "UP", prev) if upper else "NONE"
    lower_event = _bar_event(last, lower["level"], "DOWN", prev) if lower else "NONE"
    event_candidates = []
    if upper_event != "NONE":
        event_candidates.append((upper_event, upper))
    if lower_event != "NONE":
        event_candidates.append((lower_event, lower))
    # When both sides qualify in the same bar, prefer the node whose level is
    # closer to the bar close. This keeps the event attached to a real node
    # rather than arbitrarily preferring the upside node.
    observed_event, observed_node = ("NONE", None)
    if event_candidates:
        last_close = _n(last.get("close")) if last else None
        observed_event, observed_node = min(
            event_candidates,
            key=lambda item: abs(item[1]["level"] - last_close) if last_close is not None else item[1]["distance_from_price"],
        )

    return {"version":"conditional-path-v3","current_price":price,"current_node":"CURRENT",
            "upper_node":upper,"lower_node":lower,"next_up":next_up,"next_down":next_down,
            "transitions":transitions,"state":"DECISION_AREA" if upper and lower else "ONE_SIDED",
            "status":"VALID" if upper or lower else "UNKNOWN",
            "observed_last_event":observed_event,
            "observed_event_level":observed_node.get("level") if observed_node else None,
            "observed_event_node":observed_node,
            "observed_event_candidates":[
                {"event": event_name, "level": node["level"]}
                for event_name, node in event_candidates
            ]}

def _fmt_node(node):
    return f"node {node.get('level'):,.2f}" if isinstance(node,dict) and _n(node.get("level")) is not None else "node ถัดไปที่มีข้อมูล"

def compact_market_flow(price: float, path: dict[str,Any], market_state: dict[str,Any] | None=None) -> dict[str,str]:
    upper=path.get("upper_node") or {}; lower=path.get("lower_node") or {}
    up=upper.get("level"); dn=lower.get("level")
    regime=(market_state or {}).get("regime") or (market_state or {}).get("bias") or "UNKNOWN"
    if up and dn:
        read=f"ราคา {price:,.2f} อยู่ระหว่าง {dn:,.2f} และ {up:,.2f}; โครงสร้าง {regime}"
        flow=f"↑ ผ่าน {up:,.2f} และยืนได้ → {_fmt_node(path.get('next_up'))}; ↓ หลุด {dn:,.2f} และยืนต่ำกว่า → {_fmt_node(path.get('next_down'))}"
    elif up:
        read=f"ราคา {price:,.2f} อยู่ใต้ node {up:,.2f}; ต้องผ่านและยืนได้จึงเปิดทางขึ้น"
        flow=f"↑ Break + Accept {up:,.2f} → {_fmt_node(path.get('next_up'))}"
    elif dn:
        read=f"ราคา {price:,.2f} อยู่เหนือ node {dn:,.2f}; ต้องรักษาระดับ {dn:,.2f}"
        flow=f"↓ Break + Accept {dn:,.2f} → {_fmt_node(path.get('next_down'))}"
    else:
        read=f"ราคา {price:,.2f}; ยังไม่มี structural node ที่ยืนยันได้"; flow="ยังไม่มี conditional path"
    return {"read":read,"flow":flow}

def build_flow_context(parsed: dict[str,Any]) -> dict[str,Any]:
    raw=parsed.get("raw_series") or {}
    price=_n(parsed.get("cfd_price"))
    if price is None: price=_n(parsed.get("future_price"))
    if price is None: return {"version":"market-flow-context-v2","status":"UNKNOWN","reason":"CURRENT_PRICE_UNKNOWN"}
    diff=_n(parsed.get("basis_diff"))
    zones=raw.get("multi_expiry_gamma_zones") or {}; gex=raw.get("gex") or {}
    nodes=[]
    for key,role in (("call_wall","CALL_WALL"),("put_wall","PUT_WALL"),("gamma_flip","GAMMA_FLIP")):
        level=_n(gex.get(key))
        if level is not None and diff is not None:
            nodes.append({"level":level-diff,"role":role,"node_type":role,"source":"options","tier":0})
    for key in ("resistance_nodes","support_nodes"):
        for strike in zones.get(key) or []:
            level=_n(strike)
            if level is not None and diff is not None:
                nodes.append({"level":level-diff,"role":"LOCAL_GAMMA_NODE","node_type":"LOCAL_GAMMA_NODE","source":"options","tier":1})
    # Add strike-level gamma structure so the path engine can see meaningful
    # local concentrations that are not promoted to a wall. Local prominence
    # is computed from neighbouring strikes instead of a global 20% cutoff.
    rows=gex.get("rows") or []
    ordered=[]
    for row in rows:
        strike=_n(row.get("strike"))
        g=_n(row.get("net_gex"))
        if strike is None or g is None or diff is None:
            continue
        ordered.append((strike,g))
    ordered.sort(key=lambda x:x[0])
    for idx,(strike,g) in enumerate(ordered):
        neighbours=[abs(ordered[j][1]) for j in (idx-1,idx+1) if 0<=j<len(ordered)]
        local_base=(sum(neighbours)/len(neighbours)) if neighbours else 0.0
        prominence=max(0.0,abs(g)-local_base)
        if prominence <= 0 and abs(g) < 1e-9:
            continue
        nodes.append({
            "level":strike-diff,
            "role":"LOCAL_GAMMA_NODE",
            "node_type":"LOCAL_GAMMA_NODE",
            "source":"options_strike",
            "tier":1 if prominence>0 else 2,
            "local_prominence":prominence,
            "aggregate_gex":g,
            "evidence_refs":[{"type":"gex_strike","strike":strike}],
        })
    technical=parsed.get("technical_context") or {}
    memory=build_price_memory(technical.get("ohlcv") or {},current_price=price)
    # Technical price memory contributes only observed price locations; it does
    # not manufacture evenly spaced levels.
    for tf,ctx in (technical.get("timeframes") or {}).items():
        fib=ctx.get("fibonacci") or {}
        for name in ("swing_high","swing_low","retracement_62","retracement_79"):
            level=_n(fib.get(name))
            if level is not None:
                nodes.append({"level":level,"role":f"{tf.upper()}_{name.upper()}","node_type":"TECHNICAL_NODE","source":"twelve_data","tier":2})
        fvg=ctx.get("fvg") or {}
        for name in ("low","high"):
            level=_n(fvg.get(name))
            if level is not None:
                nodes.append({"level":level,"role":f"{tf.upper()}_FVG","node_type":"TECHNICAL_NODE","source":"twelve_data","tier":2})
    recent=((memory.get("timeframes") or {}).get("m5") or {}).get("bars") or []
    ranked=rank_structural_nodes(price,nodes,price_memory=memory)
    path=build_conditional_path(price,ranked,recent_bars=recent)
    path["nodes"]=ranked
    compact=compact_market_flow(price,path,(raw.get("market_state") or {}))
    return {"version":"market-flow-context-v2","status":"VALID","price_memory":memory,
            "nodes":ranked,"path":path,"market_read":compact["read"],"flow_read":compact["flow"]}

# architecture-reviewed: flow engine remains deterministic and LLM-free
