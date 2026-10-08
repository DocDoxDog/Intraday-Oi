"""Deterministic market-state enrichment and analyst output guardrails.

This module is the final evidence-first boundary before LLM delivery:
- normalized CFD levels are source-derived only
- history/flow metrics are computed from stored snapshots
- missing evidence remains UNKNOWN
- conditional trade plans are completed from deterministic levels
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import os


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    number = _num(value)
    return f"{number:,.2f}" if number is not None else "UNKNOWN"


def _ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _cfd_level(futures_level: Any, future_price: Any, cfd_price: Any) -> float | None:
    level = _num(futures_level)
    future = _num(future_price)
    cfd = _num(cfd_price)
    if level is None or future is None or cfd is None:
        return None
    return round(level - future + cfd, 5)


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    n = _num(numerator)
    d = _num(denominator)
    if n is None or d is None or d == 0:
        return None
    return round(n / d, 6)


def _totals(parsed: dict[str, Any]) -> dict[str, Any]:
    return (parsed.get("raw_series") or {}).get("totals") or {}


def _oi_values(snapshot: dict[str, Any] | None) -> dict[str, float | None]:
    raw = (snapshot or {}).get("raw_series") or {}
    totals = raw.get("totals") or {}
    return {
        "put": _num(totals.get("open_interest_view_put", totals.get("open_interest_put"))),
        "call": _num(totals.get("open_interest_view_call", totals.get("open_interest_call"))),
        "total": _num(totals.get("open_interest_view_total", totals.get("open_interest_total"))),
        "vol": _num((snapshot or {}).get("vol")),
        "churn": _num(totals.get("churn")),
        "gex": _num((raw.get("gex") or {}).get("net_gex")),
    }


def _current_oi(parsed: dict[str, Any]) -> dict[str, float | None]:
    return _oi_values(parsed)


def _period_diff(current: dict[str, float | None], base: dict[str, float | None] | None) -> dict[str, float | None]:
    if not base:
        return {key: None for key in current}
    out: dict[str, float | None] = {}
    for key, value in current.items():
        old = base.get(key)
        out[key] = round(value - old, 6) if value is not None and old is not None else None
    return out


def _history_line(label: str, diff: dict[str, float | None]) -> str:
    return (
        f"{label}: Price Δ {_fmt(diff.get('price'))} | "
        f"IV Δ {_fmt(diff.get('vol'))}% | "
        f"OI Δ Put {_fmt(diff.get('put'))} / Call {_fmt(diff.get('call'))} / Total {_fmt(diff.get('total'))} | "
        f"Churn Δ {_fmt(diff.get('churn'))} | Net GEX Δ {_fmt(diff.get('gex'))}"
    )


def _history_for(parsed: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    current = _current_oi(parsed)
    current["price"] = _num(parsed.get("future_price"))

    hour = history.get("hour_ago")
    hour_values = _oi_values(hour)
    hour_values["price"] = _num((hour or {}).get("future_price"))

    two_hour = history.get("two_hours_ago")
    two_values = _oi_values(two_hour)
    two_values["price"] = _num((two_hour or {}).get("future_price"))

    today = history.get("today") or {}
    today_values = {
        "put": _num((today.get("oi_first") or {}).get("oi_put")),
        "call": _num((today.get("oi_first") or {}).get("oi_call")),
        "total": _num((today.get("oi_first") or {}).get("oi_total")),
        "vol": _num(today.get("vol_first")),
        "churn": _num((today.get("oi_first") or {}).get("churn")),
        "gex": _num((today.get("oi_first") or {}).get("gex_net")),
        "price": _num(today.get("future_price_open")),
    }

    yesterday = history.get("yesterday") or {}
    yesterday_values = {
        "put": _num((yesterday.get("oi_last") or {}).get("oi_put")),
        "call": _num((yesterday.get("oi_last") or {}).get("oi_call")),
        "total": _num((yesterday.get("oi_last") or {}).get("oi_total")),
        "vol": _num(yesterday.get("vol_last")),
        "churn": _num((yesterday.get("oi_last") or {}).get("churn")),
        "gex": _num((yesterday.get("oi_last") or {}).get("gex_net")),
        "price": _num(yesterday.get("future_price_last")),
    }

    one_hour_diff = _period_diff(current, hour_values if hour else None)
    two_hour_prior = _period_diff(hour_values, two_values if two_hour else None)
    today_diff = _period_diff(current, today_values if today.get("count") else None)
    yesterday_diff = _period_diff(current, yesterday_values if yesterday.get("count") else None)

    return {
        "1h": one_hour_diff,
        "today": today_diff,
        "yesterday": yesterday_diff,
        "two_hour_prior": two_hour_prior,
        "summary": " | ".join([
            _history_line("1H", one_hour_diff),
            _history_line("TODAY", today_diff),
            _history_line("YESTERDAY", yesterday_diff),
        ]),
    }


def _levels(parsed: dict[str, Any]) -> dict[str, Any]:
    """Expose structural trigger anchors without manufacturing a price ladder."""
    raw = parsed.get("raw_series") or {}
    gex = raw.get("gex") or {}
    future = _num(parsed.get("future_price"))
    cfd = _num(parsed.get("cfd_price"))
    if future is None or cfd is None:
        return {
            "resistance_far": None,
            "resistance_main": None,
            "resistance_current": None,
            "support_current": None,
            "support_main": None,
            "support_deep": None,
        }

    call_wall = _num(gex.get("call_wall"))
    put_wall = _num(gex.get("put_wall"))
    return {
        "resistance_far": None,
        "resistance_main": _cfd_level(call_wall, future, cfd),
        "resistance_current": _cfd_level(call_wall, future, cfd),
        "support_current": _cfd_level(put_wall, future, cfd),
        "support_main": _cfd_level(put_wall, future, cfd),
        "support_deep": None,
    }



def _gamma_state(parsed: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    raw = parsed.get("raw_series") or {}
    gex = raw.get("gex") or {}
    rows = [
        r for r in (gex.get("rows") or [])
        if isinstance(r, dict)
        and _num(r.get("strike")) is not None
        and _num(r.get("net_gex")) is not None
    ]

    abs_total = sum(abs(_num(r.get("net_gex")) or 0) for r in rows)
    gamma_mean = (
        sum((_num(r.get("strike")) or 0) * abs(_num(r.get("net_gex")) or 0) for r in rows) / abs_total
        if abs_total
        else None
    )

    prior = (history.get("hour_ago") or {}).get("raw_series") or {}
    prior_rows = {
        _num(r.get("strike")): _num(r.get("net_gex"))
        for r in (prior.get("gex") or {}).get("rows", [])
        if isinstance(r, dict)
        and _num(r.get("strike")) is not None
        and _num(r.get("net_gex")) is not None
    }
    changes = []
    for row in rows:
        strike = _num(row.get("strike"))
        previous = prior_rows.get(strike)
        current = _num(row.get("net_gex"))
        if strike is not None and current is not None and previous is not None:
            changes.append((strike, current - previous))
    changes.sort(key=lambda item: abs(item[1]), reverse=True)

    zones = raw.get("multi_expiry_gamma_zones") or {}
    future = _num(parsed.get("future_price"))
    cfd = _num(parsed.get("cfd_price"))
    to_cfd = lambda value: _cfd_level(value, future, cfd)
    return {
        "net_gex": _num(gex.get("net_gex")),
        "call_gex": _num(gex.get("call_gex_total")),
        "put_gex": _num(gex.get("put_gex_total")),
        "gamma_mean": to_cfd(gamma_mean),
        "gamma_mean_futures": round(gamma_mean, 5) if gamma_mean is not None else None,
        "gamma_pivot": to_cfd(gex.get("gamma_flip")),
        "gamma_flip": to_cfd(gex.get("gamma_flip")),
        "positive_zone": to_cfd(zones.get("highest_positive_gamma")),
        "negative_zone": to_cfd(zones.get("highest_negative_gamma")),
        "call_wall": to_cfd(gex.get("call_wall")),
        "put_wall": to_cfd(gex.get("put_wall")),
        "acceleration_zones": [
            {"strike_futures": strike, "strike_cfd": to_cfd(strike), "gex_change": change}
            for strike, change in changes[:3]
        ],
    }


def _iv_term_structure(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for item in parsed.get("expiration_snapshots") or []:
        if not isinstance(item, dict):
            continue
        output.append({
            "code": item.get("expiration_code")
            or (item.get("raw_series") or {}).get("expiration_selection", {}).get("selected"),
            "dte": _num(item.get("dte")),
            "iv": _num(item.get("vol")),
        })
    return output


def _skew(parsed: dict[str, Any]) -> float | None:
    rows = (parsed.get("raw_series") or {}).get("strike_rows") or []
    future = _num(parsed.get("future_price"))
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        call_iv = _num(row.get("callIV", row.get("callImpliedVol")))
        put_iv = _num(row.get("putIV", row.get("putImpliedVol")))
        strike = _num(row.get("strike"))
        if call_iv is not None and put_iv is not None and strike is not None and future is not None:
            candidates.append((abs(strike - future), put_iv - call_iv))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return round(candidates[0][1], 5)


def _decision_framework(
    parsed: dict[str, Any],
    flow: dict[str, Any],
    gamma: dict[str, Any],
    levels: dict[str, float | None],
    history_state: dict[str, Any],
) -> dict[str, Any]:
    """Backward-compatible adapter to the canonical decision engine."""
    from src.decision_engine import build_decision_context

    state = {
        "flow": flow,
        "gamma": gamma,
        "levels": levels,
        "history": history_state,
        "price": {
            "futures": _num(parsed.get("future_price")),
            "cfd": _num(parsed.get("cfd_price")),
            "basis": _num(parsed.get("basis_diff")),
            "dte": _num(parsed.get("dte")),
        },
        "technical": {
            tf: technical
            for tf, technical in (
                (tf, ((parsed.get("technical_context") or {}).get("timeframes") or {}).get(tf) or {})
                for tf in ("h4", "h1", "m15", "m5", "m1")
            )
        },
        "news": parsed.get("news_context") or [],
    }
    return build_decision_context(state)["legacy_framework"]

def enrich_market_state(parsed: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    history = history or {}
    raw = parsed.setdefault("raw_series", {})
    totals = _totals(parsed)
    current = _current_oi(parsed)
    hour = history.get("hour_ago")
    hour_oi = _oi_values(hour)

    elapsed = None
    if hour:
        t_now = _ts(parsed.get("observed_at") or parsed.get("retrieved_at"))
        t_old = _ts(hour.get("captured_at") or hour.get("observed_at"))
        if t_now and t_old and t_now > t_old:
            elapsed = (t_now - t_old).total_seconds() / 3600.0

    oi_delta_put = _num(totals.get("oi_delta_put"))
    oi_delta_call = _num(totals.get("oi_delta_call"))
    oi_delta_total = _num(totals.get("oi_delta_total"))
    if oi_delta_total is None and oi_delta_put is not None and oi_delta_call is not None:
        oi_delta_total = oi_delta_put + oi_delta_call

    # Keep QuikStrike source OI Change separate from our own EOD-baseline delta.
    # They are different measurements and must never overwrite each other.
    source_oi_change_put = _num(totals.get("oi_change_put"))
    source_oi_change_call = _num(totals.get("oi_change_call"))
    source_oi_change_total = _num(totals.get("oi_change_total"))
    if source_oi_change_total is None and (
        source_oi_change_put is not None or source_oi_change_call is not None
    ):
        source_oi_change_total = sum(
            value for value in (source_oi_change_put, source_oi_change_call)
            if value is not None
        )

    # EOD = the explicit stored session baseline used by oi_positioning.
    # Derive totals from the same baseline rows; never substitute current OI.
    baseline = history.get("oi_baseline") or {}
    baseline_raw = baseline.get("raw_series") or {}
    baseline_totals = baseline_raw.get("totals") or {}
    eod_oi_put = _num(
        baseline_totals.get("open_interest_view_put", baseline_totals.get("open_interest_put"))
    )
    eod_oi_call = _num(
        baseline_totals.get("open_interest_view_call", baseline_totals.get("open_interest_call"))
    )
    eod_oi_total = _num(
        baseline_totals.get("open_interest_view_total", baseline_totals.get("open_interest_total"))
    )

    positioning_churn = (
        abs(oi_delta_put) + abs(oi_delta_call)
        if oi_delta_put is not None and oi_delta_call is not None
        else None
    )

    velocities = {
        "put": round((current["put"] - hour_oi["put"]) / elapsed, 6)
        if elapsed and current["put"] is not None and hour_oi["put"] is not None else None,
        "call": round((current["call"] - hour_oi["call"]) / elapsed, 6)
        if elapsed and current["call"] is not None and hour_oi["call"] is not None else None,
        "total": round((current["total"] - hour_oi["total"]) / elapsed, 6)
        if elapsed and current["total"] is not None and hour_oi["total"] is not None else None,
    }

    two = history.get("two_hours_ago")
    prior_velocities = {"put": None, "call": None, "total": None}
    prior_elapsed = None
    if two and hour:
        t1 = _ts(hour.get("captured_at") or hour.get("observed_at"))
        t0 = _ts(two.get("captured_at") or two.get("observed_at"))
        if t1 and t0 and t1 > t0:
            prior_elapsed = (t1 - t0).total_seconds() / 3600.0
    if prior_elapsed:
        t_oi = _oi_values(two)
        prior_velocities = {
            "put": round((hour_oi["put"] - t_oi["put"]) / prior_elapsed, 6)
            if hour_oi["put"] is not None and t_oi["put"] is not None else None,
            "call": round((hour_oi["call"] - t_oi["call"]) / prior_elapsed, 6)
            if hour_oi["call"] is not None and t_oi["call"] is not None else None,
            "total": round((hour_oi["total"] - t_oi["total"]) / prior_elapsed, 6)
            if hour_oi["total"] is not None and t_oi["total"] is not None else None,
        }

    acceleration = {
        key: round(velocities[key] - prior_velocities[key], 6)
        if velocities[key] is not None and prior_velocities[key] is not None else None
        for key in ("put", "call", "total")
    }

    technical = parsed.get("technical_context") or {}
    technical_summary = {}
    for tf in ("h4", "h1", "m15", "m5", "m1"):
        context = (technical.get("timeframes") or {}).get(tf) or {}
        technical_summary[tf] = {
            "trend": context.get("trend"),
            "ema50": _num(context.get("ema50")),
            "ema200": _num(context.get("ema200")),
            "vwap": _num(context.get("vwap")),
            "atr14": _num(context.get("atr14")),
            "fvg": context.get("fvg"),
            "volume": _num(context.get("latest_volume")),
            "momentum_5": _num(context.get("momentum_5")),
            "bos": context.get("bos"),
            "sweep": context.get("sweep"),
        }

    raw["market_state"] = {
        "flow": {
            "oi_put": current["put"],
            "oi_call": current["call"],
            "oi_total": current["total"],
            "delta_oi_put": oi_delta_put,
            "delta_oi_call": oi_delta_call,
            "delta_oi_total": oi_delta_total,
            "oi_change_put": source_oi_change_put,
            "oi_change_call": source_oi_change_call,
            "oi_change_total": source_oi_change_total,
            "eod_oi_put": eod_oi_put,
            "eod_oi_call": eod_oi_call,
            "eod_oi_total": eod_oi_total,
            "eod_available": bool(eod_oi_put is not None or eod_oi_call is not None),
            "source_churn_put": _num(totals.get("quikstrike_churn_put")),
            "source_churn_call": _num(totals.get("quikstrike_churn_call")),
            "source_churn_total": _num(totals.get("churn")),
            "positioning_churn": positioning_churn,
            "call_put_oi_ratio": _safe_ratio(current["call"], current["put"]),
            "call_put_delta_oi_ratio": _safe_ratio(oi_delta_call, oi_delta_put),
            "oi_velocity_per_hour": velocities,
            "oi_acceleration_per_hour2": acceleration,
        },
        "volatility": {
            "iv": _num(parsed.get("vol")),
            "iv_change_1h": (
                round(_num(parsed.get("vol")) - _num(hour.get("vol")), 6)
                if hour and _num(parsed.get("vol")) is not None and _num(hour.get("vol")) is not None
                else None
            ),
            "iv_term_structure": _iv_term_structure(parsed),
            "skew": _skew(parsed),
        },
        "gamma": _gamma_state(parsed, history),
        "history": _history_for(parsed, history),
        "technical": technical_summary,
        "news": [
            {
                "headline": item.get("headline"),
                "source": item.get("source"),
                "published_at": item.get("published_at"),
                "event_time": item.get("event_time"),
                "actual": item.get("actual"),
                "forecast": item.get("forecast"),
                "previous": item.get("previous"),
                "relevance": item.get("relevance"),
                "priority": "HIGH" if item.get("relevance") == "HIGH" else "MEDIUM",
                "category": item.get("category"),
                "market_channels": item.get("market_channels") or [],
                "freshness": item.get("freshness") or "UNKNOWN",
            }
            for item in (parsed.get("news_context") or [])[:8]
            if isinstance(item, dict)
        ],
        "price": {
            "futures": _num(parsed.get("future_price")),
            "cfd": _num(parsed.get("cfd_price")),
            "basis": _num(parsed.get("basis_diff")),
            "dte": _num(parsed.get("dte")),
        },
        "levels": _levels(parsed),
        "cfd_complete": (
            _num(parsed.get("future_price")) is not None
            and _num(parsed.get("cfd_price")) is not None
            and _num(parsed.get("basis_diff")) is not None
        ),
    }
    # Compose the next-generation deterministic engines without changing the
    # existing canonical OI/GEX calculations.
    from src.action_zone_engine import build_action_zones
    from src.data_clock import apply_data_clock
    from src.order_flow import build_order_flow_context
    from src.regime_engine import build_market_regime

    order_flow_input = raw.get("order_flow") or {}
    state = raw["market_state"]
    state["auction"] = technical.get("auction") or {}
    state["macro"] = raw.get("macro_state") or {}
    state["order_flow"] = build_order_flow_context(
        trades=order_flow_input.get("trades") if isinstance(order_flow_input, dict) else None,
        book=order_flow_input.get("book") if isinstance(order_flow_input, dict) else None,
    )
    state["regime"] = build_market_regime(state)
    state["action_zones"] = build_action_zones(state)

    from src.decision_engine import build_decision_context

    decision = build_decision_context(state)
    state["decision"] = decision
    # Keep legacy consumers working while making decision the canonical source.
    state["decision_framework"] = decision["legacy_framework"]

    apply_data_clock(parsed)
    return parsed


def _plan_numbers(levels: dict[str, float | None]) -> dict[str, dict[str, float | None]]:
    return {
        "long": {
            "entry": levels.get("resistance_current"),
            "stop": levels.get("support_current"),
            "tp1": levels.get("resistance_main"),
            "tp2": levels.get("resistance_far"),
        },
        "short": {
            "entry": levels.get("support_current"),
            "stop": levels.get("resistance_current"),
            "tp1": levels.get("support_main"),
            "tp2": levels.get("support_deep"),
        },
    }


def _unique_sorted(values: list[float], *, reverse: bool = False) -> list[float]:
    return sorted({round(value, 5) for value in values}, reverse=reverse)


def _deterministic_trade_levels(
    parsed: dict[str, Any],
    levels: dict[str, float | None],
    gamma: dict[str, Any],
) -> dict[str, Any]:
    """Build a single, source-derived market map for both scenarios.

    Important:
    - trigger = structural call/put wall, normalized to CFD
    - targets = real source strikes only
    - Gamma Mean / gamma zones are context, never execution targets
    - targets are deliberately separated so adjacent $5 strikes do not become
      fake R1/R2/R3 or S1/S2/S3.
    """
    future = _num(parsed.get("future_price"))
    cfd = _num(parsed.get("cfd_price"))
    raw = parsed.get("raw_series") or {}
    gex = raw.get("gex") or {}
    rows = [
        row for row in (gex.get("rows") or [])
        if isinstance(row, dict) and _num(row.get("strike")) is not None
    ]

    call_wall = _num(levels.get("resistance_main"))
    put_wall = _num(levels.get("support_main"))

    # A trade trigger is the level the market must reclaim/reject for the
    # setup to become actionable. In a bearish regime already below the
    # call wall, the short setup is a failed-retest of that broken wall;
    # using the put wall as the short trigger would put the trigger above the
    # invalidation and incorrectly erase the setup.
    decision = ((raw.get("market_state") or {}).get("decision_framework") or {})
    htf = str((((decision.get("steps") or {}).get("1_market_state") or {}).get("htf_structure") or "mixed")).lower()
    current = cfd
    # Each setup gets its own structural invalidation. Never use a distant
    # opposite wall as a generic stop: that can create absurd risk distances.
    long_trigger = call_wall
    short_trigger = put_wall
    long_stop = None
    short_stop = None
    def nearest_source_level(anchor: float | None, *, above: bool) -> float | None:
        """Return the nearest observed source strike on the requested side."""
        if anchor is None or future is None or cfd is None:
            return None
        candidates = []
        for row in rows:
            strike = _num(row.get("strike"))
            if strike is None:
                continue
            level = _cfd_level(strike, future, cfd)
            if level is None:
                continue
            if above and level > anchor:
                candidates.append(level)
            elif not above and level < anchor:
                candidates.append(level)
        if not candidates:
            return None
        return min(candidates) if above else max(candidates)

    def nearest_canonical_level(anchor: float | None, *, above: bool) -> float | None:
        if anchor is None:
            return None
        values = [
            _num(v) for k, v in levels.items()
            if k not in {"resistance_current", "support_current"}
            and _num(v) is not None
        ]
        candidates = [v for v in values if (v > anchor if above else v < anchor)]
        return min(candidates) if above and candidates else max(candidates) if candidates else None

    long_stop = (
        nearest_source_level(call_wall, above=False)
        if call_wall is not None
        else None
    ) or nearest_canonical_level(call_wall, above=False) or _num(levels.get("support_main"))
    short_stop = (
        nearest_source_level(put_wall, above=True)
        if put_wall is not None
        else None
    ) or nearest_canonical_level(put_wall, above=True) or _num(levels.get("resistance_main"))

    if htf == "bearish" and current is not None and call_wall is not None and current <= call_wall:
        # Bearish failed-retest setup: trigger is the broken call wall and
        # invalidation must sit ABOVE that trigger. Use the nearest source
        # strike above it, never an unrelated lower put wall.
        short_trigger = call_wall
        short_stop = nearest_source_level(call_wall, above=True) or nearest_canonical_level(call_wall, above=True) or _num(levels.get("resistance_main"))
    elif htf == "bullish" and current is not None and put_wall is not None and current >= put_wall:
        # Bullish failed-reclaim mirror: trigger is the broken put wall and
        # invalidation must sit BELOW that trigger.
        long_trigger = put_wall
        long_stop = nearest_source_level(put_wall, above=False) or nearest_canonical_level(put_wall, above=False) or _num(levels.get("support_main"))

    # Separate support-reaction LONG setup. It remains available even when
    # the primary regime is bearish, but still requires confirmation.
    long_support_trigger = put_wall
    long_support_stop = (
        nearest_source_level(put_wall, above=False)
        if put_wall is not None
        else None
    ) or _num(levels.get("support_deep")) or _num(levels.get("support_main"))

    def source_candidates(side: str, anchor: float | None) -> list[dict[str, float]]:
        if anchor is None or future is None or cfd is None:
            return []
        out = []
        for row in rows:
            strike = _num(row.get("strike"))
            if strike is None:
                continue
            level = _cfd_level(strike, future, cfd)
            if level is None:
                continue
            if side == "LONG" and level <= anchor:
                continue
            if side == "SHORT" and level >= anchor:
                continue
            oi = _num(row.get("oiTotal"))
            if oi is None:
                oi = _num(row.get("openInterest"))
            gex_value = _num(row.get("net_gex"))
            out.append({
                "level": level,
                "strike": strike,
                "oi": oi or 0.0,
                "gex": abs(gex_value or 0.0),
            })
        return sorted(out, key=lambda x: x["level"], reverse=side == "SHORT")

    def canonical_candidates(direction: str, anchor: float | None) -> list[float]:
        if anchor is None:
            return []
        values: list[float] = []
        for value in levels.values():
            num = _num(value)
            if num is None:
                continue
            if direction == "ABOVE" and num > anchor:
                values.append(num)
            elif direction == "BELOW" and num < anchor:
                values.append(num)
        return _unique_sorted(values, reverse=direction == "BELOW")

    # Execution uses nearby levels only. Distant walls stay in the global market map.
    # Local execution distance is volatility-normalized. Structural R/S can
    # be far away and remain valid context; only source-derived levels within
    # the configured ATR window can become executable action zones.
    technical_context = parsed.get("technical_context") or {}
    atr14 = _num(technical_context.get("atr14"))
    if atr14 is None:
        atr14 = _num((technical_context.get("m5") or {}).get("atr14"))
    try:
        local_max_atr = float(os.environ.get("LOCAL_ZONE_MAX_ATR", "1.5"))
    except (TypeError, ValueError):
        local_max_atr = 1.5
    local_max_atr = max(0.5, local_max_atr)

    try:
        local_fallback_distance = float(os.environ.get("LOCAL_TRADE_MAX_DISTANCE", "15"))
    except (TypeError, ValueError):
        local_fallback_distance = 15.0
    local_fallback_distance = max(5.0, local_fallback_distance)

    above_now = source_candidates("LONG", current)
    below_now = source_candidates("SHORT", current)
    above_levels = [item["level"] for item in above_now]
    below_levels = [item["level"] for item in below_now]
    above_levels.extend(canonical_candidates("ABOVE", current))
    below_levels.extend(canonical_candidates("BELOW", current))
    above_levels = _unique_sorted(above_levels)
    below_levels = _unique_sorted(below_levels, reverse=True)

    local_max_distance = (
        round(atr14 * local_max_atr, 5)
        if atr14 is not None and atr14 > 0
        else local_fallback_distance
    )
    local_distance_mode = "ATR" if atr14 is not None and atr14 > 0 else "FALLBACK_ABSOLUTE"


    def structural_levels(side: str, anchor: float | None) -> list[float]:
        candidates = source_candidates(side, anchor)
        if not candidates:
            return []
        # Key levels describe the nearest real source structure. They are not
        # automatically executable targets.
        return [item["level"] for item in candidates[:3]]

    def trade_targets(
        side: str,
        anchor: float | None,
        stop: float | None,
        structural: list[float],
    ) -> list[float]:
        if anchor is None or stop is None:
            return []
        risk = abs(anchor - stop)
        if risk <= 0:
            return []
        # Targets must be real structural nodes beyond the trigger.
        # Risk/reward is evaluated separately by risk_engine; it must not
        # erase valid structural targets from the customer market map.
        return [
            level for level in structural
            if (
                level > anchor
                if side == "LONG"
                else level < anchor
            )
        ][:5]

    long_candidates = source_candidates("LONG", long_trigger)
    short_candidates = source_candidates("SHORT", short_trigger)

    # Significant key levels come from the multi-expiry concentration engine.
    # They are converted to the same CFD coordinate as all execution levels.
    zone_source = (raw.get("multi_expiry_gamma_zones") or {})
    def convert_zone_nodes(values: Any) -> list[float]:
        out = []
        for value in values or []:
            converted = _cfd_level(value, future, cfd)
            if converted is not None:
                out.append(converted)
        return sorted(dict.fromkeys(out))

    long_key_levels = convert_zone_nodes(zone_source.get("resistance_nodes"))
    short_key_levels = sorted(convert_zone_nodes(zone_source.get("support_nodes")), reverse=True)

    # If multi-expiry concentration data is unavailable, derive the same
    # significance-aware nodes from the current real option chain. Never fall
    # back to "nearest five strikes" because that recreates a synthetic ladder.
    if not long_key_levels or not short_key_levels:
        try:
            from src.multi_expiry import select_structural_nodes
            aggregate = [
                (float(row["strike"]), float(row["net_gex"]))
                for row in rows
                if _num(row.get("strike")) is not None
                and _num(row.get("net_gex")) is not None
            ]
            grid = [
                float(row["strike"]) for row in rows
                if _num(row.get("strike")) is not None
            ]
            if not long_key_levels:
                long_key_levels = [
                    _cfd_level(v, future, cfd)
                    for v in select_structural_nodes(
                        [(s, g) for s, g in aggregate if g > 0],
                        current=future,
                        side="UP",
                        grid_strikes=grid,
                    )
                    if _cfd_level(v, future, cfd) is not None
                ]
            if not short_key_levels:
                short_key_levels = [
                    _cfd_level(v, future, cfd)
                    for v in select_structural_nodes(
                        [(s, g) for s, g in aggregate if g < 0],
                        current=future,
                        side="DOWN",
                        grid_strikes=grid,
                    )
                    if _cfd_level(v, future, cfd) is not None
                ]
                short_key_levels = sorted(set(short_key_levels), reverse=True)
        except Exception:
            pass

    local_action_resistance = next(
        (level for level in long_key_levels if current is not None and level - current <= local_max_distance),
        None,
    )
    local_action_support = next(
        (level for level in short_key_levels if current is not None and current - level <= local_max_distance),
        None,
    )
    def structural_targets(side: str, anchor: float | None) -> list[float]:
        if anchor is None:
            return []
        nodes = long_key_levels if side == "LONG" else short_key_levels
        if nodes:
            return [
                value for value in nodes
                if (value > anchor if side == "LONG" else value < anchor)
            ]
        # No concentration node means no structural target. Never fabricate
        # a sequential $5 target ladder from neighbouring option strikes.
        return []

    long_reclaim_trigger = local_action_resistance
    long_reclaim_stop = (
        nearest_source_level(long_reclaim_trigger, above=False)
        if long_reclaim_trigger is not None else None
    ) or nearest_canonical_level(long_reclaim_trigger, above=False)
    long_reclaim_targets = trade_targets(
        "LONG", long_reclaim_trigger, long_reclaim_stop,
        structural_targets("LONG", long_reclaim_trigger)
    )

    long_support_trigger = local_action_support
    long_support_stop = (
        nearest_source_level(long_support_trigger, above=False)
        if long_support_trigger is not None else None
    ) or nearest_canonical_level(long_support_trigger, above=False)
    long_support_targets = trade_targets(
        "LONG", long_support_trigger, long_support_stop,
        structural_targets("LONG", long_support_trigger)
    )

    short_rejection_trigger = local_action_resistance
    short_rejection_stop = (
        nearest_source_level(short_rejection_trigger, above=True)
        if short_rejection_trigger is not None else None
    ) or nearest_canonical_level(short_rejection_trigger, above=True)
    short_rejection_targets = trade_targets(
        "SHORT", short_rejection_trigger, short_rejection_stop,
        structural_targets("SHORT", short_rejection_trigger)
    )

    short_breakdown_trigger = local_action_support
    short_breakdown_stop = (
        nearest_source_level(short_breakdown_trigger, above=True)
        if short_breakdown_trigger is not None else None
    ) or nearest_canonical_level(short_breakdown_trigger, above=True)
    short_breakdown_targets = trade_targets(
        "SHORT", short_breakdown_trigger, short_breakdown_stop,
        structural_targets("SHORT", short_breakdown_trigger)
    )

    def tp_fields(values: list[float]) -> dict[str, float | None]:
        return {
            f"tp{i}": values[i - 1] if len(values) >= i else None
            for i in range(1, 6)
        }

    legacy_long_targets = trade_targets(
        "LONG", long_trigger, long_stop, structural_targets("LONG", long_trigger)
    )
    legacy_short_targets = trade_targets(
        "SHORT", short_trigger, short_stop, structural_targets("SHORT", short_trigger)
    )

    return {
        # Legacy primary aliases remain so existing consumers do not break.
        "long_trigger": long_trigger,
        "long_stop": long_stop,
        "long_key_levels": long_key_levels,
        **{f"long_tp{i}": (legacy_long_targets[i - 1] if i <= len(legacy_long_targets) else None) for i in range(1, 6)},
        "long_support_trigger": long_support_trigger,
        "long_support_stop": long_support_stop,
        **{f"long_support_tp{i}": (long_support_targets[i - 1] if i <= len(long_support_targets) else None) for i in range(1, 6)},
        "short_trigger": short_trigger,
        "short_stop": short_stop,
        "short_key_levels": short_key_levels,
        **{f"short_tp{i}": (legacy_short_targets[i - 1] if i <= len(legacy_short_targets) else None) for i in range(1, 6)},

        # Explicit four-route trade map used by the new Telegram/Dashboard UI.
        "call_wall": call_wall,
        "put_wall": put_wall,
        "local_trade_max_distance": local_max_distance,
        "local_max_atr": local_max_atr,
        "local_atr14": atr14,
        "local_distance_mode": local_distance_mode,
        "local_action_resistance": local_action_resistance,
        "local_action_support": local_action_support,
        "long_reclaim_trigger": long_reclaim_trigger,
        "long_reclaim_stop": long_reclaim_stop,
        **{f"long_reclaim_tp{i}": (long_reclaim_targets[i - 1] if i <= len(long_reclaim_targets) else None) for i in range(1, 6)},
        "short_rejection_trigger": short_rejection_trigger,
        "short_rejection_stop": short_rejection_stop,
        **{f"short_rejection_tp{i}": (short_rejection_targets[i - 1] if i <= len(short_rejection_targets) else None) for i in range(1, 6)},
        "short_breakdown_trigger": short_breakdown_trigger,
        "short_breakdown_stop": short_breakdown_stop,
        **{f"short_breakdown_tp{i}": (short_breakdown_targets[i - 1] if i <= len(short_breakdown_targets) else None) for i in range(1, 6)},
    }



def _valid_trade_ladder(plan: dict[str, Any]) -> bool:
    """Require directional ordering for every available execution TP."""
    long_values = [
        _num(plan.get("long_stop")), _num(plan.get("long_trigger")),
        *[_num(plan.get(f"long_tp{i}")) for i in range(1, 6)],
    ]
    short_values = [
        *[_num(plan.get(f"short_tp{i}")) for i in range(5, 0, -1)],
        _num(plan.get("short_trigger")), _num(plan.get("short_stop")),
    ]

    # The canonical validator below intentionally permits missing TP4/TP5 on
    # sparse snapshots; when present, all levels must remain monotonic.
    if long_values[0] is not None and long_values[1] is not None:
        present = [x for x in long_values[2:] if x is not None]
        if any(x <= long_values[1] for x in present):
            return False
        if any(present[i] >= present[i + 1] for i in range(len(present) - 1)):
            return False
    if short_values[-2] is not None and short_values[-1] is not None:
        present = [x for x in short_values[:-2] if x is not None]
        if any(x >= short_values[-2] for x in present):
            return False
        if any(present[i] <= present[i + 1] for i in range(len(present) - 1)):
            return False
    return True


def _validate_or_clear_trade_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate trigger/stop and every available TP1-TP5 without inventing values."""
    out = dict(plan)

    def validate_side(side: str) -> bool:
        prefix = "long" if side == "LONG" else "short"
        stop = _num(out.get(f"{prefix}_stop"))
        trigger = _num(out.get(f"{prefix}_trigger"))
        targets = [_num(out.get(f"{prefix}_tp{i}")) for i in range(1, 6)]

        if stop is None or trigger is None:
            return False
        if side == "LONG" and stop >= trigger:
            return False
        if side == "SHORT" and trigger >= stop:
            return False

        compact_targets: list[float] = []
        for tp in targets:
            if tp is None:
                continue
            if side == "LONG" and tp <= trigger:
                return False
            if side == "SHORT" and tp >= trigger:
                return False
            if compact_targets:
                if side == "LONG" and tp <= compact_targets[-1]:
                    return False
                if side == "SHORT" and tp >= compact_targets[-1]:
                    return False
            compact_targets.append(tp)

        # Missing TP values remain UNKNOWN; no synthetic extension is allowed.
        for i in range(1, 6):
            out[f"{prefix}_tp{i}"] = compact_targets[i - 1] if i <= len(compact_targets) else None
        return True

    long_ok = validate_side("LONG")
    short_ok = validate_side("SHORT")

    out["long_status"] = "CONDITIONAL" if long_ok else "NO_TRADE"
    out["short_status"] = "CONDITIONAL" if short_ok else "NO_TRADE"
    out["status"] = "CONDITIONAL" if long_ok or short_ok else "NO_TRADE"

    requested = str(out.get("direction") or "WAIT").upper()
    if requested == "BUY" and not long_ok:
        out["direction"] = "WAIT"
    elif requested == "SELL" and not short_ok:
        out["direction"] = "WAIT"
    elif requested not in {"BUY", "SELL", "WAIT"}:
        out["direction"] = "WAIT"

    if not long_ok:
        for i in range(1, 6):
            out[f"long_tp{i}"] = None
        out["long_trigger"] = None
        out["long_stop"] = None
    if not short_ok:
        for i in range(1, 6):
            out[f"short_tp{i}"] = None
        out["short_trigger"] = None
        out["short_stop"] = None
    return out


def _rr(side: str, p: dict[str, float | None]) -> tuple[float | None, float | None]:
    entry, stop, tp1, tp2 = p["entry"], p["stop"], p["tp1"], p["tp2"]
    if any(x is None for x in (entry, stop)):
        return None, None
    risk = (entry - stop) if side == "LONG" else (stop - entry)
    if risk <= 0:
        return None, None
    r1 = (
        (tp1 - entry) / risk
        if side == "LONG" and tp1 is not None
        else (entry - tp1) / risk
        if side == "SHORT" and tp1 is not None
        else None
    )
    r2 = (
        (tp2 - entry) / risk
        if side == "LONG" and tp2 is not None
        else (entry - tp2) / risk
        if side == "SHORT" and tp2 is not None
        else None
    )
    return (
        round(r1, 2) if r1 is not None else None,
        round(r2, 2) if r2 is not None else None,
    )


from src.trade_plan_engine import build_trade_execution_plan


def _decision_final_idea(decision: dict[str, Any]) -> str:
    structural = str(decision.get("structural_bias") or "MIXED").upper()
    tactical = str(decision.get("tactical_direction") or "NEUTRAL").upper()
    confirmation = str(decision.get("confirmation_state") or "NOT_CONFIRMED").upper()
    state = str(decision.get("decision_state") or "WAIT").upper()

    if confirmation == "CONFIRMED":
        side = "ขึ้น" if structural == "BULLISH" else "ลง" if structural == "BEARISH" else "ตาม setup ที่ยืนยัน"
        return f"โครงสร้าง {structural} และมี price confirmation แล้ว: ฝั่ง{side}อยู่ในสถานะยืนยัน"
    if structural == "MIXED":
        return f"โครงสร้างหลักยังขัดกัน ขณะ tactical เป็น {tactical}; ตอนนี้ {state} และยังไม่ยืนยันทาง"
    side = "ขึ้น" if structural == "BULLISH" else "ลง"
    return f"โครงสร้างหลักยัง{side} แต่ {confirmation}; รอ price confirmation ก่อน activate ฝั่งดังกล่าว"


def normalize_analyst_output(
    parsed: dict[str, Any],
    history: dict[str, Any] | None,
    ai_result: dict[str, Any],
) -> dict[str, Any]:
    state = (parsed.get("raw_series") or {}).get("market_state") or {}
    levels = state.get("levels") or {}
    ai = dict(ai_result or {})

    ai["levels"] = {key: _fmt(value) for key, value in levels.items()}

    history_summary = (state.get("history") or {}).get("summary")
    if history_summary:
        ai["history_comparison"] = history_summary

    if not state.get("cfd_complete") and str(ai.get("analysis_status") or "").upper() == "CONFIRMED":
        ai["analysis_status"] = "DEGRADED"

    gamma = state.get("gamma") or {}

    # When the deterministic conditional-path engine is valid, its observed
    # structural nodes become the execution-map anchors. Legacy wall-derived
    # levels remain a compatibility fallback only.
    flow = (parsed.get("raw_series") or {}).get("market_flow") or {}
    path = flow.get("path") if isinstance(flow, dict) else None
    execution_levels = dict(levels)
    if isinstance(path, dict) and path.get("status") == "VALID":
        upper = path.get("upper_node") or {}
        lower = path.get("lower_node") or {}
        next_up = path.get("next_up") or {}
        next_down = path.get("next_down") or {}
        if _num(upper.get("level")) is not None:
            execution_levels["resistance_current"] = _num(upper.get("level"))
            execution_levels["resistance_main"] = _num(upper.get("level"))
        if _num(next_up.get("level")) is not None:
            execution_levels["resistance_far"] = _num(next_up.get("level"))
        if _num(lower.get("level")) is not None:
            execution_levels["support_current"] = _num(lower.get("level"))
            execution_levels["support_main"] = _num(lower.get("level"))
        if _num(next_down.get("level")) is not None:
            execution_levels["support_deep"] = _num(next_down.get("level"))

    deterministic = _deterministic_trade_levels(parsed, execution_levels, gamma)
    plan = {
        "long": {
            "entry": deterministic["long_trigger"],
            "stop": deterministic["long_stop"],
            **{f"tp{i}": deterministic.get(f"long_tp{i}") for i in range(1, 6)},
        },
        "short": {
            "entry": deterministic["short_trigger"],
            "stop": deterministic["short_stop"],
            **{f"tp{i}": deterministic.get(f"short_tp{i}") for i in range(1, 6)},
        },
    }
    long_rr = _rr("LONG", plan["long"])
    short_rr = _rr("SHORT", plan["short"])
    has_any_numeric_plan = any(
        _num(value) is not None
        for side in plan.values()
        for value in side.values()
    )

    old_trade = ai.get("trade_plan") if isinstance(ai.get("trade_plan"), dict) else {}
    bias = str(ai.get("bias") or old_trade.get("direction") or "WAIT").upper()
    if bias not in {"BUY", "SELL", "BULLISH", "BEARISH"}:
        bias = "WAIT"
    # Customer-facing bias is a structural view; executable direction is gated
    # separately by confirmation below.
    if bias == "BULLISH":
        market_view = "BULLISH"
    elif bias == "BEARISH":
        market_view = "BEARISH"
    else:
        market_view = "WAIT"

    def plan_line(side: str, values: dict[str, float | None]) -> str:
        rr = long_rr if side == "LONG" else short_rr
        return (
            f"{side} Entry {_fmt(values['entry'])} | Stop {_fmt(values['stop'])} | "
            f"TP1 {_fmt(values['tp1'])} | TP2 {_fmt(values['tp2'])} | "
            f"RR1 {_fmt(rr[0])}R | RR2 {_fmt(rr[1])}R"
        )

    # The deterministic decision gate controls the actionability language.
    # Keep the LLM's bias as a contextual view, but never let its free-form
    # narrative invent a trigger or override contradictory structure.
    decision_context = state.get("decision") or {}
    deterministic_idea = _decision_final_idea(decision_context) if decision_context else (
        "Directional context มีอยู่ แต่ trigger/confirmation ยังไม่ครบ จึงรอ event confirmation"
    )

    deterministic_plan = {
        **deterministic,
        "status": "CONDITIONAL",
        "direction": "WAIT",
    }
    validated_plan = _validate_or_clear_trade_plan(deterministic_plan)
    plan_status = str(validated_plan.get("status") or "NO_TRADE").upper()
    requested_direction = str(validated_plan.get("direction") or "WAIT").upper()
    plan_direction = (
        "BUY" if requested_direction == "BUY" and validated_plan.get("long_status") == "CONDITIONAL"
        else "SELL" if requested_direction == "SELL" and validated_plan.get("short_status") == "CONDITIONAL"
        else "WAIT"
    )

    # Canonical market map: KEY LEVELS, SCENARIO and TRADE PLAN must all
    # consume exactly the same deterministic object. Structural gamma references
    # stay separate and can never silently become execution targets.
    pivot = _num(gamma.get("gamma_mean"))
    current_cfd = _num((state.get("price") or {}).get("cfd"))
    long_trigger_map = validated_plan["long_trigger"]
    short_trigger_map = validated_plan["short_trigger"]
    if current_cfd is not None and long_trigger_map is not None and short_trigger_map is not None:
        if short_trigger_map < current_cfd < long_trigger_map:
            location_state = "INSIDE_GAMMA_BAND"
        elif current_cfd >= long_trigger_map:
            location_state = "ABOVE_CALL_WALL"
        elif current_cfd <= short_trigger_map:
            location_state = "BELOW_PUT_WALL"
        else:
            location_state = "UNKNOWN"
    else:
        location_state = "UNKNOWN"

    long_key_levels = deterministic.get("long_key_levels") or []
    short_key_levels = deterministic.get("short_key_levels") or []
    ai["market_map"] = {
        # R/S are structural key levels, not automatic trade targets.
        "structural_resistance_nodes": list(long_key_levels),
        "structural_support_nodes": list(short_key_levels),
        "R1": long_key_levels[0] if len(long_key_levels) > 0 else None,
        "R2": long_key_levels[1] if len(long_key_levels) > 1 else None,
        "R3": long_key_levels[2] if len(long_key_levels) > 2 else None,
        "R4": long_key_levels[3] if len(long_key_levels) > 3 else None,
        "R5": long_key_levels[4] if len(long_key_levels) > 4 else None,
        "long_trigger": long_trigger_map,
        "short_trigger": short_trigger_map,
        "S1": short_key_levels[0] if len(short_key_levels) > 0 else None,
        "S2": short_key_levels[1] if len(short_key_levels) > 1 else None,
        "S3": short_key_levels[2] if len(short_key_levels) > 2 else None,
        "S4": short_key_levels[3] if len(short_key_levels) > 3 else None,
        "S5": short_key_levels[4] if len(short_key_levels) > 4 else None,
        "call_wall": deterministic.get("call_wall"),
        "put_wall": deterministic.get("put_wall"),
        "local_trade_max_distance": deterministic.get("local_trade_max_distance"),
        "local_action_resistance": deterministic.get("local_action_resistance"),
        "local_action_support": deterministic.get("local_action_support"),
        "long_reclaim_trigger": deterministic.get("long_reclaim_trigger"),
        "long_reclaim_stop": deterministic.get("long_reclaim_stop"),
        "long_reclaim_trade_targets": [deterministic.get(f"long_reclaim_tp{i}") for i in range(1, 6) if deterministic.get(f"long_reclaim_tp{i}") is not None],
        "short_rejection_trigger": deterministic.get("short_rejection_trigger"),
        "short_rejection_stop": deterministic.get("short_rejection_stop"),
        "short_rejection_trade_targets": [deterministic.get(f"short_rejection_tp{i}") for i in range(1, 6) if deterministic.get(f"short_rejection_tp{i}") is not None],
        "short_breakdown_trigger": deterministic.get("short_breakdown_trigger"),
        "short_breakdown_stop": deterministic.get("short_breakdown_stop"),
        "short_breakdown_trade_targets": [deterministic.get(f"short_breakdown_tp{i}") for i in range(1, 6) if deterministic.get(f"short_breakdown_tp{i}") is not None],
        "long_trade_targets": [
            validated_plan.get(f"long_tp{i}") for i in range(1, 6)
            if validated_plan.get(f"long_tp{i}") is not None
        ],
        "long_support_trigger": deterministic.get("long_support_trigger"),
        "long_support_invalidation": deterministic.get("long_support_stop"),
        "long_support_trade_targets": [
            deterministic.get(f"long_support_tp{i}") for i in range(1, 6)
            if deterministic.get(f"long_support_tp{i}") is not None
        ],
        "short_trade_targets": [
            validated_plan.get(f"short_tp{i}") for i in range(1, 6)
            if validated_plan.get(f"short_tp{i}") is not None
        ],
        "long_status": validated_plan.get("long_status", "UNAVAILABLE"),
        "short_status": validated_plan.get("short_status", "UNAVAILABLE"),
        "long_invalidation": validated_plan["long_stop"],
        "short_invalidation": validated_plan["short_stop"],
        "pivot": pivot,
        "location_state": location_state,
        "structural_bias": decision_context.get("structural_bias"),
        "tactical_direction": decision_context.get("tactical_direction"),
        "confirmation_state": decision_context.get("confirmation_state"),
        "decision_state": decision_context.get("decision_state"),
        "roles": {
            "call_wall": "RESISTANCE / DECISION_ZONE",
            "put_wall": "SUPPORT / DECISION_ZONE",
            "long_reclaim": "BREAKOUT_RETEST_LONG",
            "long_support": "REVERSAL_LONG",
            "short_rejection": "REVERSAL_SHORT",
            "short_breakdown": "BREAKOUT_RETEST_SHORT",
            "long_trigger": "CALL_WALL_RECLAIM",
            "long_support_trigger": "PUT_WALL_REACTION",
            "short_trigger": "CALL_WALL_RETEST" if deterministic["short_trigger"] == deterministic["long_trigger"] and deterministic["short_trigger"] is not None else "PUT_WALL_BREAKDOWN",
            "long_invalidation": "NEAREST_SOURCE_BELOW_TRIGGER",
            "long_support_invalidation": "NEAREST_SOURCE_BELOW_SUPPORT",
            "short_invalidation": "NEAREST_SOURCE_ABOVE_TRIGGER",
            "pivot": "GAMMA_MEAN",
        },
        "source": "QUIKSTRIKE_GEX_STRIKES_NORMALIZED_TO_CFD",
        "execution_targets_exclude": ["gamma_mean", "positive_gamma_zone", "negative_gex_zone", "R1", "R2", "R3", "S1", "S2", "S3"],
    }

    # Give the state machine the exact same canonical map used by rendering.
    state["market_map"] = ai["market_map"]

    # Recompute Action Zones after the canonical market map exists so the
    # customer-facing state and execution state use the same triggers.
    from src.action_zone_engine import build_action_zones
    from src.data_clock import apply_data_clock
    state["action_zones"] = build_action_zones(state)

    # Re-compose the canonical decision after the market map/action zones exist.
    # This is the final evidence -> interpretation -> confirmation boundary.
    from src.decision_engine import build_decision_context
    decision = build_decision_context(state)
    state["decision"] = decision
    state["decision_framework"] = decision["legacy_framework"]
    decision_context = decision

    # Recompute actionability from the FINAL decision object. This prevents the
    # first pre-market-map decision from leaking into trade direction/status.
    confirmed_long = bool((decision.get("confirmation") or {}).get("LONG", {}).get("confirmed"))
    confirmed_short = bool((decision.get("confirmation") or {}).get("SHORT", {}).get("confirmed"))
    structural_bias_final = str(decision.get("structural_bias") or "MIXED").upper()
    deterministic_plan["direction"] = (
        "BUY" if confirmed_long and structural_bias_final == "BULLISH" and has_any_numeric_plan
        else "SELL" if confirmed_short and structural_bias_final == "BEARISH" and has_any_numeric_plan
        else "WAIT"
    )
    validated_plan = _validate_or_clear_trade_plan(deterministic_plan)
    plan_status = str(validated_plan.get("status") or "NO_TRADE").upper()
    requested_direction = str(validated_plan.get("direction") or "WAIT").upper()
    plan_direction = (
        "BUY" if requested_direction == "BUY" and validated_plan.get("long_status") == "CONDITIONAL"
        else "SELL" if requested_direction == "SELL" and validated_plan.get("short_status") == "CONDITIONAL"
        else "WAIT"
    )

    deterministic_idea = _decision_final_idea(decision)

    # The deterministic decision engine owns directional state. LLM bias remains
    # narrative context only and can never promote an unconfirmed setup.
    ai["structural_bias"] = decision.get("structural_bias")
    ai["tactical_direction"] = decision.get("tactical_direction")
    ai["confirmation_state"] = decision.get("confirmation_state")
    ai["decision_state"] = decision.get("decision_state")
    ai["decision_conflicts"] = decision.get("conflicts") or []
    ai["what_would_confirm"] = decision.get("what_would_confirm") or {}
    ai["decision_summary"] = decision.get("summary")

    deterministic_status = str(decision.get("analysis_status") or "DEVELOPING").upper()
    if not state.get("cfd_complete"):
        deterministic_status = "DEGRADED"
    ai["analysis_status"] = deterministic_status

    structural_bias = str(decision.get("structural_bias") or "MIXED").upper()
    ai["bias"] = structural_bias if structural_bias in {"BULLISH", "BEARISH"} else "WAIT"

    apply_data_clock(parsed)

    execution_plan = build_trade_execution_plan(state)

    # From this point onward, every rendered field must come from the
    # validated plan. Never leave a stale pre-validation entry/TP string.
    plan = {
        "long": {
            "entry": validated_plan["long_trigger"],
            "stop": validated_plan["long_stop"],
            "tp1": validated_plan["long_tp1"],
            "tp2": validated_plan["long_tp2"],
            "tp3": validated_plan["long_tp3"],
            "tp4": validated_plan.get("long_tp4"),
            "tp5": validated_plan.get("long_tp5"),
        },
        "short": {
            "entry": validated_plan["short_trigger"],
            "stop": validated_plan["short_stop"],
            "tp1": validated_plan["short_tp1"],
            "tp2": validated_plan["short_tp2"],
            "tp3": validated_plan["short_tp3"],
            "tp4": validated_plan.get("short_tp4"),
            "tp5": validated_plan.get("short_tp5"),
        },
    }
    long_rr = _rr("LONG", plan["long"])
    short_rr = _rr("SHORT", plan["short"])

    ai["trade_plan"] = {
        "status": plan_status,
        "direction": plan_direction,
        "long_trigger": validated_plan["long_trigger"], "long_stop": validated_plan["long_stop"],
        **{f"long_tp{i}": validated_plan.get(f"long_tp{i}") for i in range(1, 6)},
        "short_trigger": validated_plan["short_trigger"], "short_stop": validated_plan["short_stop"],
        **{f"short_tp{i}": validated_plan.get(f"short_tp{i}") for i in range(1, 6)},
        "long_support_trigger": deterministic.get("long_support_trigger"),
        "long_support_stop": deterministic.get("long_support_stop"),
        **{f"long_support_tp{i}": deterministic.get(f"long_support_tp{i}") for i in range(1, 6)},
        "long_reclaim_trigger": deterministic.get("long_reclaim_trigger"),
        "long_reclaim_stop": deterministic.get("long_reclaim_stop"),
        **{f"long_reclaim_tp{i}": deterministic.get(f"long_reclaim_tp{i}") for i in range(1, 6)},
        "short_rejection_trigger": deterministic.get("short_rejection_trigger"),
        "short_rejection_stop": deterministic.get("short_rejection_stop"),
        **{f"short_rejection_tp{i}": deterministic.get(f"short_rejection_tp{i}") for i in range(1, 6)},
        "short_breakdown_trigger": deterministic.get("short_breakdown_trigger"),
        "short_breakdown_stop": deterministic.get("short_breakdown_stop"),
        **{f"short_breakdown_tp{i}": deterministic.get(f"short_breakdown_tp{i}") for i in range(1, 6)},
        "entry": plan_line("LONG", plan["long"]) + " | " + plan_line("SHORT", plan["short"]),
        "stop_loss": f"LONG invalidation {_fmt(plan['long']['stop'])} | SHORT invalidation {_fmt(plan['short']['stop'])}",
        "take_profit_1": f"LONG {_fmt(plan['long']['tp1'])} | SHORT {_fmt(plan['short']['tp1'])}",
        "take_profit_2": f"LONG {_fmt(plan['long']['tp2'])} | SHORT {_fmt(plan['short']['tp2'])}",
        "take_profit_3": f"LONG {_fmt(plan['long']['tp3'])} | SHORT {_fmt(plan['short']['tp3'])}",
        "setup": f"LONG: break/holdเหนือ {_fmt(plan['long']['entry'])}; SHORT: break/retest fail ใต้ {_fmt(plan['short']['entry'])}",
        "trigger": f"LONG trigger {_fmt(plan['long']['entry'])} with hold/retest | SHORT trigger {_fmt(plan['short']['entry'])} with break/retest failure",
        "confirmation": "ใช้ price action/technical confirmation จากข้อมูลที่มี; OI/ΔOI/churn เป็น context ไม่ใช่ entry โดยลำพัง",
        "invalidation": f"LONG invalidation ใต้ {_fmt(plan['long']['stop'])} | SHORT invalidation เหนือ {_fmt(plan['short']['stop'])}",
        "risk_reward": f"LONG RR1 {_fmt(long_rr[0])}R / RR2 {_fmt(long_rr[1])}R | SHORT RR1 {_fmt(short_rr[0])}R / RR2 {_fmt(short_rr[1])}R",
        "market_condition": str(ai.get("market_regime") or "UNKNOWN"),
        "position_risk": old_trade.get("position_risk") or "กำหนดขนาดความเสี่ยงหลัง trigger ตามกติกาพอร์ต",
        "risk_note": old_trade.get("risk_note") or "Conditional roadmap จาก deterministic evidence; ไม่ใช่คำสั่ง execute",
    }

    def _scenario_line(side: str, payload: dict[str, Any], available: bool) -> str:
        if not available:
            return (
                "UNAVAILABLE — ไม่มี trigger/stop/TP1 ที่เป็น source-derived ครบ"
            )
        state_name = str(payload.get("state") or "ARMED")
        trigger = _fmt(payload.get("trigger"))
        target_values = list(payload.get("targets") or [])[:3]
        target_values.extend([None] * (3 - len(target_values)))
        targets = target_values
        target_text = " → ".join(_fmt(v) for v in targets if v is not None)
        if side == "LONG":
            return (
                f"{state_name} — Break/accept เหนือ {trigger} แล้ว confirmation; "
                f"path {target_text or 'TP1 UNKNOWN'}"
            )
        return (
            f"{state_name} — Break/retest-fail ใต้ {trigger} แล้ว confirmation; "
            f"path {target_text or 'TP1 UNKNOWN'}"
        )

    long_exec = execution_plan.get("long") or {}
    short_exec = execution_plan.get("short") or {}
    long_available = validated_plan.get("long_status") == "CONDITIONAL"
    short_available = validated_plan.get("short_status") == "CONDITIONAL"
    ai["scenarios"] = {
        "bull": _scenario_line("LONG", long_exec, long_available),
        "bear": _scenario_line("SHORT", short_exec, short_available),
        "sideway": (
            f"RANGE / WAIT — ราคาอยู่ระหว่าง {_fmt(plan['short']['entry'])} ถึง {_fmt(plan['long']['entry'])}"
            if plan["short"]["entry"] is not None and plan["long"]["entry"] is not None
            else "WAIT — ยังไม่มี gamma/structural band ที่ครบ"
        ),
    }

    # Replace model-authored execution language with the deterministic gate
    # interpretation. The model still supplies the broader thesis fields.
    ai["final_trade_idea"] = _decision_final_idea(decision)
    ai["trade_plan"]["execution_state"] = execution_plan["state"]
    ai["trade_plan"]["execution_plan"] = execution_plan
    ai["market_state"] = state
    # Stable top-level accessors keep dashboard/Telegram consumers simple.
    ai["regime_engine"] = state.get("regime") or {}
    ai["action_zones"] = state.get("action_zones") or {}
    ai["auction"] = state.get("auction") or {}
    ai["order_flow"] = state.get("order_flow") or {}
    ai["macro_state"] = state.get("macro") or {}
    ai["data_clock"] = state.get("data_clock") or {}
    return ai
