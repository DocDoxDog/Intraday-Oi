"""Research-grade trade-plan snapshot and outcome evaluation.

This module is deliberately separate from execution permission. A plan can be
stored as a point-in-time hypothesis even when it is not currently executable.
That allows later accuracy measurement without changing live trading semantics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .supabase_client import get_client


HORIZONS_SECONDS = (300, 900, 1800, 3600, 14400)


def _n(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _dt(v: Any) -> datetime | None:
    if v is None:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def build_research_plans(execution_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every route with a complete deterministic risk/target map.

    No LLM confidence is used. Routes are ranked by structural alignment and
    risk validity, while all valid routes are retained for research.
    """
    routes = execution_plan.get("routes") or []
    out: list[dict[str, Any]] = []
    htf = str(execution_plan.get("htf_context") or "mixed").upper()

    for route in routes:
        if not isinstance(route, dict):
            continue
        side = str(route.get("side") or "").upper()
        if side not in {"LONG", "LONG_SUPPORT", "SHORT"}:
            continue
        entry = _n(route.get("entry_reference", route.get("trigger")))
        stop = _n(route.get("stop"))
        targets = [_n(x) for x in (route.get("targets") or [])]
        targets = [x for x in targets if x is not None]
        risk = route.get("risk") or {}
        risk_ok = str(risk.get("status") or "").upper() == "PASS"
        if entry is None or stop is None or not targets or not risk_ok:
            continue

        is_long = side.startswith("LONG")
        if is_long and not stop < entry:
            continue
        if not is_long and not stop > entry:
            continue

        aligned = (
            (is_long and htf == "BULLISH")
            or ((not is_long) and htf == "BEARISH")
        )
        out.append({
            "route": str(route.get("route") or "UNKNOWN"),
            "side": "BUY" if is_long else "SELL",
            "entry": entry,
            "stop_loss": stop,
            "targets": targets[:5],
            "state_at_snapshot": str(route.get("state") or "UNKNOWN"),
            "execution_ready_at_snapshot": bool(route.get("execution_ready")),
            "risk_status": "PASS",
            "structural_alignment": "ALIGNED" if aligned else "COUNTERTREND_OR_TRANSITION",
            "rank": 0,
            "source": "deterministic_trade_plan_engine",
            "plan_version": str(execution_plan.get("version") or "trade-plan-v4"),
            "payload": route,
        })

    # Aligned plans first; then confirmed/triggered states; then route order.
    state_rank = {
        "CONFIRMED": 0,
        "TRIGGERED": 1,
        "TRIGGERED_WAIT_CONFIRMATION": 2,
        "IN_ZONE": 3,
        "APPROACHING": 4,
        "ARMED": 5,
    }
    out.sort(key=lambda x: (
        0 if x["structural_alignment"] == "ALIGNED" else 1,
        state_rank.get(x["state_at_snapshot"], 99),
        x["route"],
    ))
    for i, item in enumerate(out, 1):
        item["rank"] = i
    return out


def _bar_hit(side: str, bar: dict[str, Any], level: float) -> bool:
    high, low = _n(bar.get("high")), _n(bar.get("low"))
    if high is None or low is None:
        return False
    return high >= level and low <= level


def _entry_hit(side: str, bar: dict[str, Any], entry: float) -> bool:
    # The research label treats a future OHLC bar touching the entry as a fill
    # candidate. It does not claim tick-level execution quality.
    return _bar_hit(side, bar, entry)


def _first_bar_hit(side: str, bar: dict[str, Any], stop: float, target: float) -> str | None:
    stop_hit = _bar_hit(side, bar, stop)
    target_hit = _bar_hit(side, bar, target)
    if stop_hit and target_hit:
        # OHLC cannot tell which barrier was hit first. Conservative research
        # convention: stop wins.
        return "SL_AND_TP_SAME_BAR_CONSERVATIVE_SL"
    if stop_hit:
        return "SL"
    if target_hit:
        return "TP"
    return None


def evaluate_plan(plan: dict[str, Any], bars: list[dict[str, Any]], horizon_seconds: int) -> dict[str, Any]:
    as_of = _dt(plan.get("observed_at"))
    if as_of is None:
        return {"outcome_state": "UNKNOWN", "reason": "INVALID_PLAN_TIME"}

    deadline = as_of + timedelta(seconds=horizon_seconds)
    future = [
        b for b in bars
        if (dt := _dt(b.get("bar_time"))) is not None and as_of < dt <= deadline
    ]
    future.sort(key=lambda b: _dt(b.get("bar_time")) or deadline)

    entry = _n(plan.get("entry"))
    stop = _n(plan.get("stop_loss"))
    targets = [_n(x) for x in (plan.get("targets") or [])]
    targets = [x for x in targets if x is not None][:5]
    side = str(plan.get("side") or "").upper()

    if entry is None or stop is None or not targets or side not in {"BUY", "SELL"}:
        return {"outcome_state": "UNKNOWN", "reason": "INCOMPLETE_PLAN"}

    entry_time = None
    entry_index = None
    for i, bar in enumerate(future):
        if _entry_hit(side, bar, entry):
            entry_time = _dt(bar.get("bar_time"))
            entry_index = i
            break

    if entry_index is None:
        return {
            "horizon_seconds": horizon_seconds,
            "observed_at": future[-1].get("bar_time") if future else None,
            "entry_touched": False,
            "entry_time": None,
            "first_exit": None,
            "outcome_state": "NO_ENTRY_TOUCH",
            "bars_observed": len(future),
        }

    path = future[entry_index:]
    mfe_values: list[float] = []
    mae_values: list[float] = []
    target_times: dict[int, str | None] = {i: None for i in range(1, len(targets) + 1)}
    first_exit = None
    exit_time = None

    for bar in path:
        high, low = _n(bar.get("high")), _n(bar.get("low"))
        if high is None or low is None:
            continue
        if side == "BUY":
            mfe_values.append((high - entry) / entry)
            mae_values.append((low - entry) / entry)
        else:
            mfe_values.append((entry - low) / entry)
            mae_values.append((entry - high) / entry)

        bar_time = _dt(bar.get("bar_time"))
        if bar_time is None:
            continue

        # Once the entry is touched, record every TP that the bar reaches.
        for idx, target in enumerate(targets, 1):
            if target_times[idx] is None and _bar_hit(side, bar, target):
                target_times[idx] = bar_time.isoformat()

        if first_exit is None:
            target1 = targets[0]
            hit = _first_bar_hit(side, bar, stop, target1)
            if hit:
                first_exit = hit
                exit_time = bar_time

    last_close = _n(path[-1].get("close")) if path else None
    forward_return = (
        ((last_close - entry) / entry) if side == "BUY"
        else ((entry - last_close) / entry)
    ) if last_close is not None and entry else None

    result = {
        "horizon_seconds": horizon_seconds,
        "observed_at": future[-1].get("bar_time") if future else None,
        "entry_touched": True,
        "entry_time": entry_time.isoformat() if entry_time else None,
        "stop_hit": first_exit is not None and first_exit.startswith("SL"),
        "stop_time": exit_time.isoformat() if first_exit and first_exit.startswith("SL") else None,
        "first_exit": first_exit,
        "forward_return": forward_return,
        "mfe": max(mfe_values) if mfe_values else None,
        "mae": min(mae_values) if mae_values else None,
        "bars_observed": len(future),
        "outcome_state": (
            "STOP_LOSS"
            if first_exit and first_exit.startswith("SL")
            else "TAKE_PROFIT"
            if first_exit and first_exit.startswith("TP")
            else "TIMEOUT"
        ),
        "metrics": {
            "research_convention": "OHLC_TOUCH; SAME_BAR_SL_WINS",
            "target_count": len(targets),
            "horizon_seconds": horizon_seconds,
        },
    }
    for idx in range(1, 6):
        stamp = target_times.get(idx)
        result[f"tp{idx}_hit"] = stamp is not None
        result[f"tp{idx}_time"] = stamp
    return result


def evaluate_pending_plans(*, instrument: str = "XAU/USD") -> int:
    """Refresh outcome rows for all stored plans using only later H1/M5 bars."""
    client = get_client()
    plans_result = (
        client.table("trade_plan_snapshots")
        .select("*")
        .eq("instrument", instrument)
        .order("observed_at", desc=False)
        .limit(500)
        .execute()
    )
    plans = plans_result.data or []
    if not plans:
        return 0

    earliest = min((_dt(x.get("observed_at")) for x in plans if _dt(x.get("observed_at"))), default=None)
    if earliest is None:
        return 0
    latest = datetime.now(timezone.utc)

    bars_result = (
        client.table("market_bars")
        .select("bar_time,open,high,low,close,volume")
        .eq("source", "twelve_data")
        .eq("instrument", instrument)
        .eq("timeframe", "m5")
        .gte("bar_time", earliest.isoformat())
        .lte("bar_time", latest.isoformat())
        .order("bar_time", desc=False)
        .range(0, 9999)
        .execute()
    )
    bars = bars_result.data or []

    written = 0
    for plan in plans:
        for horizon in HORIZONS_SECONDS:
            outcome = evaluate_plan(plan, bars, horizon)
            payload = {
                "plan_id": plan["id"],
                "horizon_seconds": horizon,
                **{k: v for k, v in outcome.items() if k not in {"horizon_seconds", "metrics"}},
                "metrics": outcome.get("metrics") or {},
            }
            client.table("trade_plan_outcomes").upsert(
                payload,
                on_conflict="plan_id,horizon_seconds",
            ).execute()
            written += 1
    return written


def summarize_plan_accuracy(*, instrument: str = "XAU/USD", horizon_seconds: int = 3600) -> dict[str, Any]:
    """Return empirical outcome stats from already-observed plan outcomes."""
    client = get_client()
    result = (
        client.table("trade_plan_outcomes")
        .select(
            "plan_id,horizon_seconds,entry_touched,stop_hit,tp1_hit,first_exit,"
            "forward_return,mfe,mae,outcome_state"
        )
        .eq("horizon_seconds", horizon_seconds)
        .order("created_at", desc=False)
        .limit(5000)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {
            "status": "NO_DATA",
            "instrument": instrument,
            "horizon_seconds": horizon_seconds,
            "sample_count": 0,
        }

    # Join outcome rows to plans so route/side are not inferred from outcome text.
    plan_ids = [x.get("plan_id") for x in rows if x.get("plan_id") is not None]
    plans = {}
    if plan_ids:
        plan_result = (
            client.table("trade_plan_snapshots")
            .select("id,route,side,structural_bias,regime")
            .in_("id", plan_ids)
            .execute()
        )
        plans = {x["id"]: x for x in (plan_result.data or [])}

    touched = [x for x in rows if x.get("entry_touched")]
    tp1 = [x for x in touched if x.get("tp1_hit")]
    sl = [x for x in touched if str(x.get("first_exit") or "").startswith("SL")]
    mfe = [_n(x.get("mfe")) for x in touched if _n(x.get("mfe")) is not None]
    mae = [_n(x.get("mae")) for x in touched if _n(x.get("mae")) is not None]

    by_route: dict[str, dict[str, Any]] = {}
    for row in touched:
        plan = plans.get(row.get("plan_id")) or {}
        key = str(plan.get("route") or "UNKNOWN")
        bucket = by_route.setdefault(key, {"samples": 0, "tp1": 0, "stop": 0})
        bucket["samples"] += 1
        bucket["tp1"] += int(bool(row.get("tp1_hit")))
        bucket["stop"] += int(str(row.get("first_exit") or "").startswith("SL"))

    for bucket in by_route.values():
        n = bucket["samples"]
        bucket["tp1_rate"] = bucket["tp1"] / n if n else None
        bucket["stop_first_rate"] = bucket["stop"] / n if n else None

    return {
        "status": "VALID",
        "instrument": instrument,
        "horizon_seconds": horizon_seconds,
        "sample_count": len(rows),
        "entry_touched": len(touched),
        "entry_touch_rate": len(touched) / len(rows) if rows else None,
        "tp1_hit_rate_after_entry": len(tp1) / len(touched) if touched else None,
        "stop_first_rate_after_entry": len(sl) / len(touched) if touched else None,
        "timeout_or_open_rate_after_entry": (
            sum(str(x.get("first_exit") or "") == "" for x in touched) / len(touched)
            if touched else None
        ),
        "mean_mfe": sum(mfe) / len(mfe) if mfe else None,
        "mean_mae": sum(mae) / len(mae) if mae else None,
        "by_route": by_route,
        "method": "empirical_forward_outcomes_only",
    }
