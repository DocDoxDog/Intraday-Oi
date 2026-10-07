"""Deterministic OHLCV bar-proxy auction/profile context."""
from __future__ import annotations
from collections import defaultdict
from typing import Any

def _num(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None

def _bin(price: float, size: float) -> float:
    return round(round(price / size) * size, 5)

def build_auction_profile(candles: list[dict[str, Any]] | None,
                          bin_size: float = 0.5,
                          value_area_pct: float = 0.70,
                          initial_balance_minutes: int = 60) -> dict[str, Any]:
    candles = [x for x in (candles or []) if isinstance(x, dict)]
    if not candles:
        return {"version":"auction-v1","status":"UNKNOWN","mode":"BAR_PROXY","approximation":"CALENDAR_DAY_APPROX"}
    valid = []
    for x in candles:
        o,h,l,c,v = map(_num, (x.get("open"),x.get("high"),x.get("low"),x.get("close"),x.get("volume")))
        if None in (h,l,c,v) or h < l or v < 0:
            continue
        valid.append({"datetime":x.get("datetime"),"open":o,"high":h,"low":l,"close":c,"volume":v})
    if not valid:
        return {"version":"auction-v1","status":"UNKNOWN","mode":"BAR_PROXY","approximation":"CALENDAR_DAY_APPROX"}
    profile = defaultdict(float)
    tpo = defaultdict(int)
    for x in valid:
        tp = (x["high"] + x["low"] + x["close"]) / 3.0
        profile[_bin(tp, bin_size)] += x["volume"]
        lo, hi = _bin(x["low"], bin_size), _bin(x["high"], bin_size)
        p = lo
        guard = 0
        while p <= hi + bin_size * 0.1 and guard < 2000:
            tpo[round(p,5)] += 1
            p += bin_size
            guard += 1
    ordered = sorted(profile.items())
    poc = max(ordered, key=lambda kv: kv[1])[0]
    total = sum(profile.values())
    target = total * value_area_pct
    included = {poc}
    left = ordered.index((poc, profile[poc])) - 1
    right = left + 2
    acc = profile[poc]
    while acc < target and (left >= 0 or right < len(ordered)):
        lv = ordered[left][1] if left >= 0 else -1
        rv = ordered[right][1] if right < len(ordered) else -1
        if rv >= lv and right < len(ordered):
            included.add(ordered[right][0]); acc += rv; right += 1
        elif left >= 0:
            included.add(ordered[left][0]); acc += lv; left -= 1
        else:
            break
    vah, val = max(included), min(included)
    ranked = sorted(profile.items(), key=lambda kv: kv[1], reverse=True)
    hvn = [p for p,v in ranked[:3]]
    lvn = [p for p,v in sorted(profile.items(), key=lambda kv: kv[1])[:3]]
    session_high = max(x["high"] for x in valid)
    session_low = min(x["low"] for x in valid)
    return {
        "version":"auction-v1","status":"OK","mode":"BAR_PROXY",
        "approximation":"CALENDAR_DAY_APPROX",
        "observed_at": valid[-1].get("datetime"),
        "bin_size": bin_size,"value_area_pct": value_area_pct,
        "poc": poc,"vah":vah,"val":val,"hvn":hvn,"lvn":lvn,
        "session_high":session_high,"session_low":session_low,
        "initial_balance": {"status":"APPROX_FIRST_60M","high":None,"low":None,"minutes":initial_balance_minutes},
        "tpo": [{"price":p,"count":tpo[p]} for p in sorted(tpo)],
        "limitations":["Profile is derived from OHLCV bars, not true tick-by-tick executed volume.",
                       "Initial Balance is metadata-only until session timestamps are mapped explicitly."],
    }
