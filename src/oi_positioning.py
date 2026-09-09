"""Derive OI positioning from two real OI snapshots; never call it volume."""
from __future__ import annotations


def _rows(snapshot: dict | None) -> dict[float, dict]:
    raw = (snapshot or {}).get("raw_series") or {}
    rows = raw.get("oi_positioning_rows") or raw.get("strike_rows") or []
    return {float(r["strike"]): r for r in rows if r.get("strike") is not None}


def enrich(current: dict, baseline: dict | None) -> dict:
    raw = current.setdefault("raw_series", {})
    current_rows = raw.get("oi_positioning_rows") or raw.get("strike_rows") or []
    old = _rows(baseline)
    out = []
    for row in current_rows:
        strike = row.get("strike")
        if strike is None:
            continue
        before = old.get(float(strike), {})
        put = float(row.get("oiPut") or 0)
        call = float(row.get("oiCall") or 0)
        old_put = float(before.get("oiPut") or 0)
        old_call = float(before.get("oiCall") or 0)
        put_delta = put - old_put
        call_delta = call - old_call
        # Churn is a positioning-activity proxy, not traded volume.
        churn = abs(put_delta) + abs(call_delta)
        item = dict(row)
        item.update({"eod_oi_put": old_put, "eod_oi_call": old_call,
                     "oi_delta_put": put_delta, "oi_delta_call": call_delta,
                     "oi_delta_total": put_delta + call_delta,
                     "churn": churn,
                     "churn_level": "high" if churn >= 100 else "medium" if churn >= 25 else "low"})
        out.append(item)
    raw["oi_positioning_rows"] = out
    raw["oi_baseline"] = {"captured_at": (baseline or {}).get("captured_at"), "available": bool(old)}
    raw["oi_positioning"] = {"definition": "Current OI vs EOD baseline; not traded volume", "baseline": raw["oi_baseline"], "rows": out}
    totals = raw.setdefault("totals", {})
    totals["oi_delta_put"] = sum(r["oi_delta_put"] for r in out)
    totals["oi_delta_call"] = sum(r["oi_delta_call"] for r in out)
    totals["churn"] = sum(r["churn"] for r in out)
    totals["oi_baseline_available"] = bool(old)
    return current
