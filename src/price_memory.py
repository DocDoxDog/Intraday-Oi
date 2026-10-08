"""Price-memory helpers for Intraday-Oi.

OHLC is source data, not an LLM inference. Twelve Data bars are persisted in
Supabase market_bars and summarized into a compact price-memory evidence block.
"""

from __future__ import annotations

from typing import Any


def _n(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _bar_summary(bars: list[dict], limit: int = 24) -> dict[str, Any]:
    valid = [
        b for b in bars
        if isinstance(b, dict)
        and _n(b.get("open")) is not None
        and _n(b.get("high")) is not None
        and _n(b.get("low")) is not None
        and _n(b.get("close")) is not None
    ]
    if not valid:
        return {"status": "UNKNOWN", "count": 0}

    recent = valid[-limit:]
    highs = [_n(b["high"]) for b in valid]
    lows = [_n(b["low"]) for b in valid]
    closes = [_n(b["close"]) for b in valid]
    last = valid[-1]
    first = valid[0]

    path = []
    for b in recent:
        path.append({
            "time": b.get("datetime"),
            "open": _n(b.get("open")),
            "high": _n(b.get("high")),
            "low": _n(b.get("low")),
            "close": _n(b.get("close")),
        })

    direction = "FLAT"
    if closes[-1] > closes[0]:
        direction = "UP"
    elif closes[-1] < closes[0]:
        direction = "DOWN"

    # Recent local extremes are observations, not synthetic targets.
    swing_high = max(x for x in highs if x is not None)
    swing_low = min(x for x in lows if x is not None)

    return {
        "status": "VALID",
        "count": len(valid),
        "first_time": first.get("datetime"),
        "last_time": last.get("datetime"),
        "first_close": closes[0],
        "last_close": closes[-1],
        "path_direction": direction,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "path": path,
    }


def build_price_memory(candles_by_tf: dict[str, list[dict]]) -> dict[str, Any]:
    return {
        "version": "price-memory-v1",
        "source": "twelve_data",
        "timeframes": {
            tf: _bar_summary(candles, limit=32 if tf in {"m5", "m15"} else 16)
            for tf, candles in candles_by_tf.items()
        },
        "role": "observed_ohlc_path_and_structure",
        "limitations": [
            "OHLC bars describe price path; they do not prove aggressor-side order flow.",
            "Swing levels are observed price structure, not guaranteed support/resistance.",
        ],
    }
