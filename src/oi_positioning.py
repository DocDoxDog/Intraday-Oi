"""Derive OI positioning from two real OI snapshots; never call it volume."""
from __future__ import annotations


def _rows(snapshot: dict | None) -> dict[float, dict]:
    raw = (snapshot or {}).get("raw_series") or {}
    rows = raw.get("oi_positioning_rows") or raw.get("strike_rows") or []
    return {float(r["strike"]): r for r in rows if r.get("strike") is not None}


def enrich(current: dict, baseline: dict | None) -> dict:
    raw = current.setdefault("raw_series", {})
    current_rows = raw.get("oi_positioning_rows") or raw.get("strike_rows") or []
    baseline_available = baseline is not None and bool(_rows(baseline))
    old = _rows(baseline)
    out = []
    for row in current_rows:
        strike = row.get("strike")
        if strike is None:
            continue
        before = old.get(float(strike))
        put = float(row.get("oiPut")) if isinstance(row.get("oiPut"), (int, float)) else None
        call = float(row.get("oiCall")) if isinstance(row.get("oiCall"), (int, float)) else None
        old_put = float(before.get("oiPut")) if before and isinstance(before.get("oiPut"), (int, float)) else None
        old_call = float(before.get("oiCall")) if before and isinstance(before.get("oiCall"), (int, float)) else None
        put_delta = put - old_put if before and put is not None and old_put is not None else None
        call_delta = call - old_call if before and call is not None and old_call is not None else None
        # Churn is a positioning-activity proxy, not traded volume.
        churn = (abs(put_delta) + abs(call_delta)) if put_delta is not None and call_delta is not None else None
        item = dict(row)
        item.update({"eod_oi_put": old_put, "eod_oi_call": old_call,
                     "oi_delta_put": put_delta, "oi_delta_call": call_delta,
                     "oi_delta_total": (put_delta + call_delta) if put_delta is not None and call_delta is not None else None,
                     "churn": churn,
                     "churn_level": ("high" if churn >= 100 else "medium" if churn >= 25 else "low") if churn is not None else "unknown"})
        out.append(item)
    raw["oi_positioning_rows"] = out
    raw["oi_baseline"] = {"captured_at": (baseline or {}).get("captured_at"), "available": baseline_available}
    raw["oi_positioning"] = {"definition": "Current OI vs previous available baseline; not traded volume", "baseline": raw["oi_baseline"], "rows": out}
    totals = raw.setdefault("totals", {})
    totals["oi_delta_put"] = sum(r["oi_delta_put"] for r in out if r["oi_delta_put"] is not None)
    totals["oi_delta_call"] = sum(r["oi_delta_call"] for r in out if r["oi_delta_call"] is not None)
    totals["churn"] = sum(r["churn"] for r in out if r["churn"] is not None)
    if not baseline_available:
        totals["oi_delta_put"] = None
        totals["oi_delta_call"] = None
        totals["oi_delta_total"] = None
        totals["churn"] = None
    else:
        totals["oi_delta_total"] = totals["oi_delta_put"] + totals["oi_delta_call"]
    totals["oi_baseline_available"] = baseline_available
    return current
