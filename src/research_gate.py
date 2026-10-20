"""V6 research governance: point-in-time eligibility, purge/embargo, OOS and cost gates."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any

VERSION="research-gate-v6.0"

def _dt(x):
    try: return datetime.fromisoformat(str(x).replace("Z","+00:00"))
    except (TypeError,ValueError): return None

def point_in_time_ok(information_time, asof):
    a,e=_dt(asof),_dt(information_time)
    return bool(a and e and e<=a)

def purged_split(rows:list[dict[str,Any]], train_end:str, test_start:str, embargo_minutes:int=0):
    te,ts=_dt(train_end),_dt(test_start)
    if not te or not ts: return {"train":[],"test":[],"rejected":len(rows),"reason":"INVALID_SPLIT"}
    embargo=timedelta(minutes=max(0,embargo_minutes)); train=[]; test=[]; rejected=[]
    for r in rows:
        t=_dt(r.get("information_time") or r.get("timestamp"))
        if not t: rejected.append(r); continue
        if t<=te and t < ts-embargo: train.append(r)
        elif t>=ts+embargo: test.append(r)
        else: rejected.append(r)
    return {"train":train,"test":test,"rejected":rejected,"embargo_minutes":embargo_minutes}

def cost_gate(gross_return:float|None, round_trip_cost:float|None, safety_margin:float=0.0):
    if gross_return is None or round_trip_cost is None: return {"status":"DATA_INSUFFICIENT"}
    net=gross_return-round_trip_cost-safety_margin
    return {"status":"PASS" if net>0 else "FAIL","gross_return":gross_return,"round_trip_cost":round_trip_cost,"net_after_cost":net}

def promotion_decision(*, measurement_pass:bool, association_pass:bool, oos_pass:bool, cost_pass:bool, calibration_pass:bool) -> dict[str,Any]:
    gates={"measurement":measurement_pass,"association":association_pass,"oos":oos_pass,"cost":cost_pass,"calibration":calibration_pass}
    return {"version":VERSION,"status":"PROMOTE" if all(gates.values()) else "REJECT_OR_ITERATE","gates":gates,
            "production_change_allowed":False,"reason":"Human/governed promotion required even when research gates pass."}
