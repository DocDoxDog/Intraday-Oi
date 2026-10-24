"""Leakage-safe multi-horizon market memory.

The memory layer is descriptive. It never creates a trade signal or probability.
All windows are cut at as_of so the current analysis cannot see future bars.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sqrt
from statistics import pstdev
from typing import Any

from .supabase_client import get_client


HORIZONS = {
    "1H": timedelta(hours=1),
    "4H": timedelta(hours=4),
    "1D": timedelta(days=1),
    "1W": timedelta(days=7),
    "1M": timedelta(days=30),
    "1Y": timedelta(days=365),
}


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def _n(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for old, new in zip(closes, closes[1:]):
        if old:
            out.append(new / old - 1.0)
    return out


def _window_summary(rows: list[dict[str, Any]], *, as_of: datetime, horizon: str) -> dict[str, Any]:
    if not rows:
        return {"status": "UNKNOWN", "horizon": horizon, "reason": "NO_HISTORY"}

    closes = [_n(x.get("close")) for x in rows]
    highs = [_n(x.get("high")) for x in rows]
    lows = [_n(x.get("low")) for x in rows]
    closes = [x for x in closes if x is not None]
    highs = [x for x in highs if x is not None]
    lows = [x for x in lows if x is not None]
    if not closes:
        return {"status": "UNKNOWN", "horizon": horizon, "reason": "NO_CLOSES"}

    first = closes[0]
    last = closes[-1]
    high = max(highs) if highs else None
    low = min(lows) if lows else None
    ret = last / first - 1.0 if first else None
    range_abs = high - low if high is not None and low is not None else None
    position = (
        (last - low) / range_abs
        if range_abs is not None and range_abs > 0
        else None
    )
    rets = _returns(closes)
    realized = pstdev(rets) * sqrt(len(rets)) if rets else None

    first_dt = _dt(rows[0].get("bar_time"))
    last_dt = _dt(rows[-1].get("bar_time"))
    coverage_hours = (
        (last_dt - first_dt).total_seconds() / 3600.0
        if first_dt and last_dt else None
    )

    # Simple descriptive slope, normalized by range. It is not a predictive score.
    slope = None
    if len(closes) >= 2 and range_abs and range_abs > 0:
        slope = (last - first) / range_abs

    state = "UP" if ret is not None and ret > 0 else "DOWN" if ret is not None and ret < 0 else "FLAT"
    if position is not None:
        location = "NEAR_HIGH" if position >= 0.8 else "NEAR_LOW" if position <= 0.2 else "MID_RANGE"
    else:
        location = "UNKNOWN"

    return {
        "status": "VALID",
        "horizon": horizon,
        "as_of": as_of.isoformat(),
        "data_start": first_dt.isoformat() if first_dt else None,
        "data_end": last_dt.isoformat() if last_dt else None,
        "bars": len(rows),
        "coverage_hours": round(coverage_hours, 2) if coverage_hours is not None else None,
        "open": first,
        "last": last,
        "high": high,
        "low": low,
        "return": ret,
        "range": range_abs,
        "range_position": position,
        "realized_vol_proxy": realized,
        "slope_over_range": slope,
        "direction": state,
        "location": location,
    }


def _fetch_h1(instrument: str, as_of: datetime) -> list[dict[str, Any]]:
    client = get_client()
    start = as_of - HORIZONS["1Y"]
    result = (
        client.table("market_bars")
        .select("bar_time,open,high,low,close,volume")
        .eq("source", "twelve_data")
        .eq("instrument", instrument)
        .eq("timeframe", "h1")
        .gte("bar_time", start.isoformat())
        .lte("bar_time", as_of.isoformat())
        .order("bar_time", desc=False)
        .range(0, 9999)
        .execute()
    )
    return result.data or []


def _option_anchor_memory(contract: str | None, as_of: datetime) -> dict[str, Any]:
    """Sparse option-state anchors, deliberately not a raw history dump."""
    if not contract:
        return {"status": "UNKNOWN", "reason": "CONTRACT_MISSING"}

    client = get_client()
    prefix = str(contract).strip()
    anchors: dict[str, Any] = {}
    for horizon, delta in HORIZONS.items():
        start = as_of - delta
        try:
            result = (
                client.table("options_flow_snapshots")
                .select("captured_at,future_price,vol,raw_series")
                .gte("captured_at", start.isoformat())
                .lte("captured_at", as_of.isoformat())
                .ilike("contract", prefix + "%")
                .order("captured_at", desc=False)
                .limit(1)
                .execute()
            )
            row = (result.data or [None])[0]
            if not row:
                anchors[horizon] = {"status": "UNKNOWN"}
                continue
            raw = row.get("raw_series") or {}
            totals = raw.get("totals") or {}
            gex = raw.get("gex") or {}
            anchors[horizon] = {
                "status": "VALID",
                "captured_at": row.get("captured_at"),
                "future_price": row.get("future_price"),
                "iv": row.get("vol"),
                "oi_put": totals.get("open_interest_view_put", totals.get("open_interest_put")),
                "oi_call": totals.get("open_interest_view_call", totals.get("open_interest_call")),
                "oi_total": totals.get("open_interest_view_total", totals.get("open_interest_total")),
                "gex": gex.get("net_gex"),
                "gamma_flip": gex.get("gamma_flip"),
                "call_wall": gex.get("call_wall"),
                "put_wall": gex.get("put_wall"),
            }
        except Exception:
            anchors[horizon] = {"status": "UNKNOWN"}

    return {"status": "PARTIAL" if anchors else "UNKNOWN", "anchors": anchors}


def build_historical_memory(
    *,
    instrument: str = "XAU/USD",
    contract: str | None = None,
    as_of: Any | None = None,
) -> dict[str, Any]:
    """Build 1H/4H/1D/1W/1M/1Y point-in-time memory from stored bars."""
    as_of_dt = _dt(as_of) if as_of is not None else datetime.now(timezone.utc)
    if as_of_dt is None:
        raise ValueError("HISTORICAL_MEMORY_AS_OF_INVALID")

    try:
        bars = _fetch_h1(instrument, as_of_dt)
    except Exception as exc:
        return {
            "version": "historical-memory-v1",
            "status": "UNKNOWN",
            "as_of": as_of_dt.isoformat(),
            "error": type(exc).__name__,
            "timeframes": {},
            "options": {"status": "UNKNOWN"},
        }

    bars = [x for x in bars if _dt(x.get("bar_time")) is not None and _dt(x.get("bar_time")) <= as_of_dt]
    bars.sort(key=lambda x: _dt(x.get("bar_time")) or as_of_dt)

    timeframes: dict[str, Any] = {}
    for horizon, delta in HORIZONS.items():
        start = as_of_dt - delta
        rows = [x for x in bars if start <= (_dt(x.get("bar_time")) or start) <= as_of_dt]
        timeframes[horizon] = _window_summary(rows, as_of=as_of_dt, horizon=horizon)

    coverage_start = _dt(bars[0].get("bar_time")) if bars else None
    return {
        "version": "historical-memory-v1",
        "status": "VALID" if bars else "UNKNOWN",
        "as_of": as_of_dt.isoformat(),
        "instrument": instrument,
        "coverage": {
            "bars": len(bars),
            "start": coverage_start.isoformat() if coverage_start else None,
            "end": as_of_dt.isoformat(),
            "days": round((as_of_dt - coverage_start).total_seconds() / 86400.0, 2) if coverage_start else 0,
        },
        "timeframes": timeframes,
        "options": _option_anchor_memory(contract, as_of_dt),
        "rules": [
            "All windows are cut at as_of; no future bars are included.",
            "Historical memory is context, not a directional signal.",
            "Sparse or missing history remains UNKNOWN/PARTIAL.",
            "Option anchors are point-in-time snapshots, not reconstructed trade flow.",
        ],
    }
