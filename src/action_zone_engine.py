"""Action-zone semantics built from deterministic market context.

A price crossing a level is not itself a setup event. This module identifies
observable proxy events from supplied timeframe structure and exposes the four
customer-facing routes:

- BUY breakout/reclaim of resistance
- BUY reaction from support
- SELL rejection at resistance
- SELL breakdown/retest below support
"""
from __future__ import annotations

from typing import Any


def _n(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _tf(s: dict[str, Any], tf: str) -> dict[str, Any]:
    return (s.get("technical") or {}).get(tf) or {}


def _trend(s: dict[str, Any], tf: str) -> str:
    return str(_tf(s, tf).get("trend") or "").lower()


def _bos(s: dict[str, Any], tf: str) -> str:
    return str(_tf(s, tf).get("bos") or "").lower()


def _is_long_bos(bos: str) -> bool:
    return bos in {"bullish", "bull", "up", "bos_up", "bullish_bos", "break_up"}


def _is_short_bos(bos: str) -> bool:
    return bos in {"bearish", "bear", "down", "bos_down", "bearish_bos", "break_down"}


def _distance_state(current: float | None, zone: float | None, tolerance: float) -> str:
    if current is None or zone is None:
        return "WAIT"
    d = abs(current - zone)
    if d <= tolerance:
        return "IN_ZONE"
    if d <= tolerance * 3:
        return "APPROACHING"
    return "WAIT"


def _setup(
    name: str,
    side: str,
    zone: float | None,
    state: str,
    action: str,
    event: str,
    invalidation: str,
    evidence: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "setup_type": name,
        "side": side,
        "zone_price": zone,
        "state": state,
        "action": action,
        "event_required": event,
        "invalidation": invalidation,
        "evidence": evidence or [],
        "limitations": limitations or [],
    }


def build_action_zones(market_state: dict[str, Any]) -> dict[str, Any]:
    price = market_state.get("price") or {}
    current = _n(price.get("cfd"))
    levels = market_state.get("levels") or {}
    market_map = market_state.get("market_map") or {}
    regime = market_state.get("regime") or {}
    auction = market_state.get("auction") or {}
    flow = market_state.get("order_flow") or {}

    # Four explicit customer-facing structural anchors. Legacy aliases are
    # accepted so older snapshots continue to render.
    call_wall = (
        _n(market_map.get("call_wall"))
        or _n(market_map.get("long_reclaim_trigger"))
        or _n(market_map.get("long_trigger"))
        or _n(levels.get("resistance_main"))
        or _n(levels.get("resistance_current"))
    )
    put_wall = (
        _n(market_map.get("put_wall"))
        or _n(market_map.get("short_breakdown_trigger"))
        or _n(market_map.get("long_support_trigger"))
        or _n(market_map.get("short_trigger"))
        or _n(levels.get("support_main"))
        or _n(levels.get("support_current"))
    )
    # Action-state display follows the local execution map. Global Call/Put
    # Walls remain market-map context and are never immediate entries.
    local_resistance = _n(market_map.get("local_action_resistance"))
    local_support = _n(market_map.get("local_action_support"))
    long_reclaim = local_resistance
    long_support = local_support
    short_rejection = local_resistance
    short_breakdown = local_support

    atr = _n((_tf(market_state, "m5")).get("atr14"))
    bin_size = _n(auction.get("bin_size"))
    tolerance = max((atr * 0.25 if atr else 0.0), (bin_size if bin_size else 0.0), 0.5)

    m15 = _trend(market_state, "m15")
    m5 = _trend(market_state, "m5")
    bos = _bos(market_state, "m5")
    m5_data = _tf(market_state, "m5")
    prev_close = _n(m5_data.get("previous_close"))

    # These are observable candle/technical proxies. They do not pretend to
    # prove hidden order-book acceptance or dealer inventory.
    breakout_long = (
        long_reclaim is not None
        and current is not None
        and current > long_reclaim
        and _is_long_bos(bos)
    )
    breakout_short = (
        short_breakdown is not None
        and current is not None
        and current < short_breakdown
        and _is_short_bos(bos)
    )
    retest_long = (
        breakout_long
        and prev_close is not None
        and abs(prev_close - long_reclaim) <= tolerance * 2
    )
    retest_short = (
        breakout_short
        and prev_close is not None
        and abs(prev_close - short_breakdown) <= tolerance * 2
    )

    sell_sweep = str(m5_data.get("sweep") or "").lower() == "sell_side_sweep"
    buy_sweep = str(m5_data.get("sweep") or "").lower() == "buy_side_sweep"

    near_long_reclaim = current is not None and long_reclaim is not None and abs(current - long_reclaim) <= tolerance
    near_long_support = current is not None and long_support is not None and abs(current - long_support) <= tolerance
    near_short_rejection = current is not None and short_rejection is not None and abs(current - short_rejection) <= tolerance
    near_short_breakdown = current is not None and short_breakdown is not None and abs(current - short_breakdown) <= tolerance

    reversal_long_event = near_long_support and (sell_sweep or _is_long_bos(bos))
    reversal_short_event = near_short_rejection and (buy_sweep or _is_short_bos(bos))

    flow_hypotheses = [
        str(x.get("type"))
        for x in flow.get("hypotheses") or []
        if isinstance(x, dict) and x.get("type")
    ]
    flow_note = (
        "flow evidence supplied"
        if flow.get("status") == "OK"
        else "order-flow evidence unavailable"
    )
    htf = str(regime.get("bias") or "MIXED").upper()
    regime_name = str(regime.get("regime") or "UNKNOWN").upper()

    # Regime does not delete the opposite-side plan. It only controls whether
    # a setup is naturally preferred by the broader market state.
    pullback_long_state = (
        "TRIGGERED" if htf == "BULLISH" and near_long_reclaim and _is_long_bos(bos)
        else _distance_state(current, long_reclaim, tolerance) if htf == "BULLISH"
        else "WAIT"
    )
    pullback_short_state = (
        "TRIGGERED" if htf == "BEARISH" and near_short_rejection and _is_short_bos(bos)
        else _distance_state(current, short_rejection, tolerance) if htf == "BEARISH"
        else "WAIT"
    )

    breakout_long_state = (
        "TRIGGERED" if retest_long
        else "IN_ZONE" if near_long_reclaim
        else "APPROACHING" if breakout_long
        else _distance_state(current, long_reclaim, tolerance)
    )
    breakout_short_state = (
        "TRIGGERED" if retest_short
        else "IN_ZONE" if near_short_breakdown
        else "APPROACHING" if breakout_short
        else _distance_state(current, short_breakdown, tolerance)
    )
    reversal_long_state = (
        "TRIGGERED" if reversal_long_event
        else _distance_state(current, long_support, tolerance)
    )
    reversal_short_state = (
        "TRIGGERED" if reversal_short_event
        else _distance_state(current, short_rejection, tolerance)
    )

    setups = {
        "pullback_long": _setup(
            "PULLBACK",
            "LONG",
            long_reclaim,
            pullback_long_state,
            "buy continuation",
            "trend + retrace into zone + reaction + bullish structure",
            "loss of continuation structure",
            [f"REGIME={regime_name}", f"M15={m15}", f"M5={m5}", f"M5_BOS={bos}", flow_note],
        ),
        "pullback_short": _setup(
            "PULLBACK",
            "SHORT",
            short_rejection,
            pullback_short_state,
            "sell continuation",
            "trend + retrace into zone + rejection + bearish structure",
            "reclaim of continuation structure",
            [f"REGIME={regime_name}", f"M15={m15}", f"M5={m5}", f"M5_BOS={bos}", flow_note],
        ),
        "breakout_retest_long": _setup(
            "BREAKOUT_RETEST",
            "LONG",
            long_reclaim,
            breakout_long_state,
            "break → hold → retest → buy",
            "breakout + acceptance proxy + retest hold",
            "return below breakout structure",
            [f"breakout={breakout_long}", f"retest={retest_long}", f"M5_BOS={bos}", flow_note],
            ["Candle data cannot prove full order-book acceptance."],
        ),
        "breakout_retest_short": _setup(
            "BREAKOUT_RETEST",
            "SHORT",
            short_breakdown,
            breakout_short_state,
            "break → retest fail → sell",
            "breakdown + acceptance proxy + retest failure",
            "reclaim above breakdown structure",
            [f"breakdown={breakout_short}", f"retest={retest_short}", f"M5_BOS={bos}", flow_note],
            ["Candle data cannot prove full order-book acceptance."],
        ),
        "reversal_long": _setup(
            "REVERSAL",
            "LONG",
            long_support,
            reversal_long_state,
            "support → reaction → buy",
            "support interaction + rejection/absorption + bullish BOS",
            "acceptance below support",
            [f"sell_sweep={sell_sweep}", f"M5_BOS={bos}", flow_note] + flow_hypotheses,
            ["Rejection/absorption is a candidate unless tick/book evidence exists."],
        ),
        "reversal_short": _setup(
            "REVERSAL",
            "SHORT",
            short_rejection,
            reversal_short_state,
            "resistance → rejection → sell",
            "resistance interaction + rejection/absorption + bearish BOS",
            "acceptance above resistance",
            [f"buy_sweep={buy_sweep}", f"M5_BOS={bos}", flow_note] + flow_hypotheses,
            ["Rejection/absorption is a candidate unless tick/book evidence exists."],
        ),
    }

    return {
        "version": "action-zone-v3",
        "status": "OK",
        "tolerance": tolerance,
        "setups": setups,
        "summary": [
            key
            for key, value in setups.items()
            if value.get("state") not in {"WAIT", "NO_TRADE"}
        ],
    }
