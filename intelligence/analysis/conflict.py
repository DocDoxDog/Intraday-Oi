"""Evidence conflict detection. Conflicts reduce certainty; they never force a direction."""
from __future__ import annotations
from typing import Any

def detect_conflicts(*, facts: list[dict[str,Any]], interpretations: list[dict[str,Any]]|None=None) -> list[dict[str,Any]]:
    domains={}
    for f in facts:
        d=str(f.get("domain","UNKNOWN")).upper()
        s=str(f.get("statement","")).lower()
        domains.setdefault(d,[]).append(s)
    out=[]
    technical=" ".join(domains.get("TECHNICAL",[])+domains.get("PRICE",[]))
    options=" ".join(domains.get("OPTIONS",[]))
    macro=" ".join(domains.get("MACRO",[])+domains.get("NEWS",[]))
    bullish=any(x in technical for x in ("bullish","higher high","bullish bos"))
    bearish=any(x in technical for x in ("bearish","lower low","bearish bos"))
    option_bull=any(x in options for x in ("positive","supportive","bullish"))
    option_bear=any(x in options for x in ("negative","bearish","pressuring"))
    if (bullish and option_bear) or (bearish and option_bull):
        out.append({"id":"C_OPTIONS_TECHNICAL","domains":["OPTIONS","TECHNICAL"],"severity":"HIGH","description":"Options evidence and price structure point in different directions.","resolution":"Use conditional scenarios; do not force a single directional conclusion."})
    if bullish and bearish:
        out.append({"id":"C_STRUCTURE_MIXED","domains":["TECHNICAL"],"severity":"MEDIUM","description":"Timeframes contain opposing structural evidence.","resolution":"Require lower-timeframe trigger before directional plan."})
    if macro and (bullish or bearish):
        out.append({"id":"C_EVENT_MARKET","domains":["NEWS","TECHNICAL"],"severity":"MEDIUM","description":"Macro/news context may conflict with observed technical path.","resolution":"Treat event risk as a scenario modifier, not a deterministic direction."})
    return out
