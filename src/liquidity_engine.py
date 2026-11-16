"""Liquidity-first market context for Intraday-Oi.

Liquidity is an execution/timing layer, not a replacement for the deterministic
HTF directional bias or the options/OI context.

Rules:
- BUY setup prefers a sell-side liquidity sweep (low taken and reclaimed).
- SELL setup prefers a buy-side liquidity sweep (high taken and rejected).
- H4/D1 levels are external liquidity / targets.
- M15/M5 levels are internal liquidity / entry timing.
- No sweep means the directional thesis may remain valid, but execution stays PENDING.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _n(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique(values: list[float | None], *, reverse: bool = False) -> list[float]:
    return sorted({round(v, 5) for v in values if v is not None}, reverse=reverse)


def _tf_liquidity(tf: str, context: dict[str, Any]) -> dict[str, Any]:
    fib = context.get("fibonacci") or {}
    prior_high = _n(context.get("prior_high"))
    prior_low = _n(context.get("prior_low"))
    swing_high = _n(fib.get("swing_high"))
    swing_low = _n(fib.get("swing_low"))
    sweep = str(context.get("sweep") or "none").lower()

    high = prior_high if prior_high is not None else swing_high
    low = prior_low if prior_low is not None else swing_low

    event = None
    level = None
    side = None
    if sweep == "buy_side_sweep":
        event, level, side = "BUY_SIDE_SWEEP", high, "SHORT"
    elif sweep == "sell_side_sweep":
        event, level, side = "SELL_SIDE_SWEEP", low, "LONG"

    return {
        "timeframe": tf,
        "high": high,
        "low": low,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "sweep": sweep,
        "event": event,
        "event_level": level,
        "event_side": side,
        "bos": context.get("bos"),
        "choch": context.get("choch"),
    }


def _session_window(observed_at: Any) -> dict[str, Any]:
    if not observed_at or ZoneInfo is None:
        return {"name": "UNKNOWN", "active": None, "timezone": "America/New_York"}

    try:
        dt = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return {"name": "UNKNOWN", "active": None, "timezone": "America/New_York"}
        ny = dt.astimezone(ZoneInfo("America/New_York"))
    except (TypeError, ValueError):
        return {"name": "UNKNOWN", "active": None, "timezone": "America/New_York"}

    # New York opening window: 08:30-11:30 local time on weekdays.
    active = ny.weekday() < 5 and time(8, 30) <= ny.time() < time(11, 30)
    return {
        "name": "NEW_YORK_OPEN",
        "active": active,
        "timezone": "America/New_York",
        "local_time": ny.strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_liquidity_context(state: dict[str, Any]) -> dict[str, Any]:
    technical = state.get("technical") or {}
    contexts = {
        tf: _tf_liquidity(tf, context if isinstance(context, dict) else {})
        for tf, context in technical.items()
        if tf in {"d1", "h4", "h1", "m15", "m5", "m1"}
    }

    # External liquidity is ordered by timeframe authority: D1 first,
    # then H4. Within each timeframe preserve the source's high/low hierarchy.
    # This keeps major session targets ahead of nearer H4 levels.
    def _priority_unique(values: list[float | None]) -> list[float]:
        out: list[float] = []
        seen: set[float] = set()
        for value in values:
            if value is None:
                continue
            rounded = round(float(value), 5)
            if rounded in seen:
                continue
            seen.add(rounded)
            out.append(rounded)
        return out

    external_highs = _priority_unique([
        (contexts.get("d1") or {}).get("high"),
        (contexts.get("d1") or {}).get("swing_high"),
        (contexts.get("h4") or {}).get("high"),
        (contexts.get("h4") or {}).get("swing_high"),
    ])
    external_lows = _priority_unique([
        (contexts.get("d1") or {}).get("low"),
        (contexts.get("d1") or {}).get("swing_low"),
        (contexts.get("h4") or {}).get("low"),
        (contexts.get("h4") or {}).get("swing_low"),
    ])

    internal_highs = _unique([
        (contexts.get("m15") or {}).get("high"),
        (contexts.get("m15") or {}).get("swing_high"),
        (contexts.get("m5") or {}).get("high"),
        (contexts.get("m5") or {}).get("swing_high"),
        (contexts.get("m1") or {}).get("high"),
        (contexts.get("m1") or {}).get("swing_high"),
    ])
    internal_lows = _unique([
        (contexts.get("m15") or {}).get("low"),
        (contexts.get("m15") or {}).get("swing_low"),
        (contexts.get("m5") or {}).get("low"),
        (contexts.get("m5") or {}).get("swing_low"),
        (contexts.get("m1") or {}).get("low"),
        (contexts.get("m1") or {}).get("swing_low"),
    ], reverse=True)

    sweeps = []
    for tf in ("m1", "m5", "m15", "h1", "h4", "d1"):
        item = contexts.get(tf) or {}
        if item.get("event"):
            sweeps.append({
                "timeframe": tf,
                "event": item["event"],
                "side": item["event_side"],
                "level": item["event_level"],
                "bos": item.get("bos"),
                "choch": item.get("choch"),
            })

    structural_bias = str(
        (state.get("decision") or {}).get("structural_bias")
        or "MIXED"
    ).upper()
    preferred_event = (
        "SELL_SIDE_SWEEP" if structural_bias == "BULLISH"
        else "BUY_SIDE_SWEEP" if structural_bias == "BEARISH"
        else None
    )
    preferred_sweeps = [x for x in sweeps if x["event"] == preferred_event]
    latest_preferred = preferred_sweeps[0] if preferred_sweeps else None

    current = _n((state.get("price") or {}).get("cfd"))
    target_highs = [x for x in external_highs if current is None or x > current]
    target_lows = [x for x in external_lows if current is None or x < current]

    session = _session_window(state.get("observed_at") or state.get("captured_at"))

    if preferred_event is None:
        gate = "MIXED_STRUCTURE"
    elif latest_preferred:
        gate = "SWEEP_DETECTED"
    else:
        gate = "SWEEP_PENDING"

    return {
        "version": "liquidity-first-v1",
        "structural_bias": structural_bias,
        "external": {
            "highs": external_highs,
            "lows": external_lows,
            "long_targets": target_highs[:5],
            "short_targets": target_lows[:5],
        },
        "internal": {
            "highs": internal_highs,
            "lows": internal_lows,
        },
        "sweeps": sweeps,
        "preferred_event": preferred_event,
        "latest_preferred_sweep": latest_preferred,
        "gate": gate,
        "entry_rule": (
            "BUY_AFTER_SELL_SIDE_SWEEP" if preferred_event == "SELL_SIDE_SWEEP"
            else "SELL_AFTER_BUY_SIDE_SWEEP" if preferred_event == "BUY_SIDE_SWEEP"
            else "WAIT_FOR_DIRECTIONAL_STRUCTURE"
        ),
        "session_window": session,
        "rules": [
            "Direction comes from HTF structure; liquidity controls timing.",
            "BUY follows a sell-side sweep; SELL follows a buy-side sweep.",
            "External H4/D1 liquidity is the preferred destination.",
            "M15/M5 liquidity is used for entry timing.",
            "No sweep means no chase; execution remains PENDING.",
        ],
    }
