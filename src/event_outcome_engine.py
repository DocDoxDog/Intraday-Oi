"""Deterministic event -> outcome measurement for the market-flow path.

No prediction is performed here. Given a timestamped event and later OHLC bars,
this module measures what actually happened at fixed horizons.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HORIZONS_SECONDS = (300, 900, 1800, 3600)


def _n(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def measure_outcome(
    event: dict[str, Any],
    bars: list[dict[str, Any]],
    nodes: list[dict[str, Any]] | None = None,
    horizon_seconds: int = 900,
) -> dict[str, Any] | None:
    """Measure an event against bars strictly after event_time.

    The event bar itself is excluded to prevent look-ahead. A horizon is measured
    from event_time and only bars whose timestamps fall inside that window count.
    """
    event_time = _dt(event.get("event_time") or event.get("detected_at"))
    level = _n(event.get("level"))
    if event_time is None or level is None:
        return None

    future = []
    for bar in bars or []:
        t = _dt(bar.get("bar_time") or bar.get("datetime"))
        close = _n(bar.get("close"))
        high = _n(bar.get("high"))
        low = _n(bar.get("low"))
        if t is None or close is None or t <= event_time:
            continue
        future.append((t, close, high, low))
    future.sort(key=lambda x: x[0])
    cutoff = event_time.timestamp() + int(horizon_seconds)
    window = [x for x in future if x[0].timestamp() <= cutoff]
    if not window:
        return None

    last = window[-1]
    event_price = _n((event.get("evidence") or {}).get("current_price"))
    if event_price is None:
        event_price = level
    if event_price == 0:
        return None

    highs = [x[2] for x in window if x[2] is not None]
    lows = [x[3] for x in window if x[3] is not None]
    forward_return = (last[1] - event_price) / event_price

    direction = str(event.get("direction") or "").upper()
    if direction == "DOWN":
        mfe = (event_price - min(lows)) / event_price if lows else None
        mae = (event_price - max(highs)) / event_price if highs else None
    else:
        mfe = (max(highs) - event_price) / event_price if highs else None
        mae = (min(lows) - event_price) / event_price if lows else None

    signed_return = forward_return if direction != "DOWN" else -forward_return
    outcome_state = "FAVORABLE" if signed_return > 0 else "ADVERSE" if signed_return < 0 else "FLAT"

    next_node_hit = None
    next_node_id = None
    time_to_next = None
    ordered_nodes = sorted(
        [n for n in (nodes or []) if isinstance(n, dict) and _n(n.get("level")) is not None],
        key=lambda n: abs(_n(n.get("level")) - event_price),
    )
    for node in ordered_nodes:
        node_level = _n(node.get("level"))
        if node_level is None or abs(node_level - event_price) < 1e-9:
            continue
        if direction == "UP" and node_level <= event_price:
            continue
        if direction == "DOWN" and node_level >= event_price:
            continue
        if node_level > event_price:
            hit_bar = next((b for b in window if b[2] is not None and b[2] >= node_level), None)
        else:
            hit_bar = next((b for b in window if b[3] is not None and b[3] <= node_level), None)
        if hit_bar:
            next_node_hit = node_level
            next_node_id = node.get("id")
            time_to_next = int((hit_bar[0] - event_time).total_seconds())
            break

    return {
        "observed_at": last[0].isoformat(),
        "forward_return": forward_return,
        "forward_range": (max(highs) - min(lows)) if highs and lows else None,
        "mfe": mfe,
        "mae": mae,
        "next_node_hit": next_node_hit,
        "next_node_id": next_node_id,
        "time_to_next_node_seconds": time_to_next,
        "outcome_state": outcome_state,
        "metrics": {
            "event_price": event_price,
            "direction": direction,
            "bars_observed": len(window),
            "horizon_seconds": int(horizon_seconds),
        },
    }
