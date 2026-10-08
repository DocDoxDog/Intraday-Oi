"""Deterministic market-flow engine: price memory -> structural nodes -> conditional path.

No synthetic levels are created. This module is deliberately independent from LLMs.
"""
from __future__ import annotations
from typing import Any

def _n(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None

def _nearest(candidates: list[dict[str, Any]], price: float, direction: str) -> dict[str, Any] | None:
    valid=[x for x in candidates if _n(x.get("level")) is not None]
    if direction=="UP":
        valid=[x for x in valid if x["level"]>price]
        return min(valid,key=lambda x:x["level"],default=None)
    valid=[x for x in valid if x["level"]<price]
    return max(valid,key=lambda x:x["level"],default=None)

def _recent_price_path(bars: list[dict[str, Any]], limit: int=12) -> list[dict[str, Any]]:
    out=[]
    for b in bars[-limit:]:
        c=_n(b.get("close"))
        if c is not None:
            out.append({"time":b.get("bar_time") or b.get("datetime"),"open":_n(b.get("open")),
                        "high":_n(b.get("high")),"low":_n(b.get("low")),"close":c})
    return out

def build_price_memory(bars_by_tf: dict[str,list[dict[str,Any]]], current_price: float | None=None) -> dict[str,Any]:
    memory={}
    for tf,bars in bars_by_tf.items():
        ordered=sorted(bars,key=lambda x:str(x.get("bar_time") or x.get("datetime") or ""))
        if not ordered: continue
        last=ordered[-1]
        closes=[_n(x.get("close")) for x in ordered if _n(x.get("close")) is not None]
        if not closes: continue
        window=ordered[-50:]
        hi=max(_n(x.get("high")) for x in window if _n(x.get("high")) is not None)
        lo=min(_n(x.get("low")) for x in window if _n(x.get("low")) is not None)
        memory[tf]={"last_close":_n(last.get("close")),"recent_high":hi,"recent_low":lo,
                    "distance_from_high":round(_n(last.get("close"))-hi,5) if hi is not None else None,
                    "distance_from_low":round(_n(last.get("close"))-lo,5) if lo is not None else None,
                    "bars":_recent_price_path(ordered)}
    return {"version":"price-memory-v1","current_price":current_price,"timeframes":memory,
            "status":"VALID" if memory else "UNKNOWN"}

def rank_structural_nodes(
    price: float,
    options_nodes: list[dict[str,Any]] | None=None,
    technical_nodes: list[dict[str,Any]] | None=None,
    price_memory: dict[str,Any] | None=None,
    max_nodes: int=12,
) -> list[dict[str,Any]]:
    """Rank real observed nodes; never manufacture a price ladder."""
    raw=(options_nodes or [])+(technical_nodes or [])
    candidates=[]
    seen=set()
    for x in raw:
        level=_n(x.get("level",x.get("strike_cfd",x.get("price"))))
        if level is None or level<=0: continue
        key=round(level,5)
        if key in seen: continue
        seen.add(key)
        distance=abs(level-price)
        source=x.get("source") or ("options" if "strike_cfd" in x else "technical")
        prominence=_n(x.get("local_prominence")) or _n(x.get("aggregate_gex")) or 0.0
        role=x.get("role") or x.get("node_type") or "STRUCTURAL_NODE"
        tier=x.get("tier")
        if tier is None:
            tier=0 if str(x.get("node_type","")).upper() in {"CALL_WALL","PUT_WALL","GAMMA_FLIP"} else 1
        candidates.append({
            "level":key,"futures_level":_n(x.get("futures_level")),
            "source":source,"role":role,"tier":tier,
            "direction":"UP" if level>price else "DOWN",
            "distance_from_price":round(distance,5),
            "local_prominence":prominence,
            "evidence_refs":x.get("evidence_refs") or [],
        })
    # Strong nearby observed nodes first, then distance. Keep the original evidence.
    candidates.sort(key=lambda x:(int(x["tier"]), -abs(float(x["local_prominence"])), x["distance_from_price"]))
    return candidates[:max_nodes]

def build_conditional_path(price: float, nodes: list[dict[str,Any]], technical: dict[str,Any] | None=None) -> dict[str,Any]:
    up=sorted([n for n in nodes if n["level"]>price],key=lambda n:n["level"])
    down=sorted([n for n in nodes if n["level"]<price],key=lambda n:n["level"],reverse=True)
    upper=up[0] if up else None
    lower=down[0] if down else None
    next_up=up[1] if len(up)>1 else None
    next_down=down[1] if len(down)>1 else None
    transitions=[]
    if upper:
        transitions.append({"from":"CURRENT","to":upper["level"],"condition_type":"BREAK_ACCEPT",
                            "condition":{"close_above":upper["level"],"acceptance_required":True},
                            "mechanism":"upside structural node","state":"ARMED"})
        if next_up:
            transitions.append({"from":upper["level"],"to":next_up["level"],"condition_type":"BREAK_ACCEPT",
                                "condition":{"close_above":next_up["level"],"acceptance_required":True},
                                "mechanism":"continuation to next observed node","state":"ARMED"})
    if lower:
        transitions.append({"from":"CURRENT","to":lower["level"],"condition_type":"BREAK_ACCEPT",
                            "condition":{"close_below":lower["level"],"acceptance_required":True},
                            "mechanism":"downside structural node","state":"ARMED"})
        if next_down:
            transitions.append({"from":lower["level"],"to":next_down["level"],"condition_type":"BREAK_ACCEPT",
                                "condition":{"close_below":next_down["level"],"acceptance_required":True},
                                "mechanism":"continuation to next observed node","state":"ARMED"})
    if lower:
        transitions.append({"from":lower["level"],"to":"CURRENT","condition_type":"RECLAIM",
                            "condition":{"close_above":lower["level"],"reclaim_required":True},
                            "mechanism":"failed downside break","state":"ARMED"})
    if upper:
        transitions.append({"from":upper["level"],"to":"CURRENT","condition_type":"RECLAIM",
                            "condition":{"close_below":upper["level"],"reclaim_required":True},
                            "mechanism":"failed upside break","state":"ARMED"})
    return {"version":"conditional-path-v2","current_price":price,
            "current_node":"CURRENT","upper_node":upper,"lower_node":lower,
            "next_up":next_up,"next_down":next_down,"transitions":transitions,
            "state":"DECISION_AREA" if upper and lower else "ONE_SIDED",
            "status":"VALID" if upper or lower else "UNKNOWN"}

def compact_market_flow(price: float, path: dict[str,Any], market_state: dict[str,Any] | None=None) -> dict[str,str]:
    upper=path.get("upper_node") or {}; lower=path.get("lower_node") or {}
    up=upper.get("level"); dn=lower.get("level")
    regime=(market_state or {}).get("regime") or (market_state or {}).get("bias") or "UNKNOWN"
    current=f"ราคา {price:,.2f}"
    if up and dn:
        read=f"{current} อยู่ระหว่าง {dn:,.2f} และ {up:,.2f}; โครงสร้างหลัก {regime} จึงรอให้ราคาเลือกทางที่ node ใด node หนึ่ง"
        flow=f"↑ ผ่าน {up:,.2f} และยืนได้ → ไป node ถัดไป; ↓ หลุด {dn:,.2f} และยืนต่ำกว่า → ลง node ถัดไป; ↩️ หลุดแล้ว reclaim → กลับเข้าสู่ node เดิม"
    elif up:
        read=f"{current} อยู่ใต้ node {up:,.2f}; ต้องผ่านและยืนได้จึงเปิดทางขึ้น"
        flow=f"↑ Break + Accept {up:,.2f} → node ถัดไป; ↩️ ผ่านแล้ว reclaim ไม่ได้ → กลับมาทดสอบราคาปัจจุบัน"
    elif dn:
        read=f"{current} อยู่เหนือ node {dn:,.2f}; ต้องรักษาระดับนี้ไว้เพื่อไม่เปิด downside path"
        flow=f"↓ Break + Accept {dn:,.2f} → node ถัดไป; ↩️ หลุดแล้ว reclaim → downside break ถูกลดน้ำหนัก"
    else:
        read=f"{current}; ยังไม่มี structural node ที่ยืนยันได้"
        flow="ยังไม่สร้าง path เพราะข้อมูลโครงสร้างไม่พอ"
    return {"read":read,"flow":flow}
