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


def _levels(parsed: dict[str, Any]) -> dict[str, float | None]:
    raw = parsed.get("raw_series") or {}
    gex = raw.get("gex") or {}
    rows = [
        row for row in (gex.get("rows") or [])
        if isinstance(row, dict) and _num(row.get("strike")) is not None
    ]
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

    strikes = sorted({_num(row.get("strike")) for row in rows if _num(row.get("strike")) is not None})
    above = [x for x in strikes if x > future]
    below = [x for x in strikes if x < future]
    call_wall = _num(gex.get("call_wall"))
    put_wall = _num(gex.get("put_wall"))

    resistance_main = _cfd_level(call_wall, future, cfd)
    support_main = _cfd_level(put_wall, future, cfd)
    resistance_current_fut = above[0] if above else call_wall
    support_current_fut = below[-1] if below else put_wall

    above_wall = [x for x in strikes if call_wall is not None and x > call_wall]
    below_wall = [x for x in strikes if put_wall is not None and x < put_wall]

    return {
        "resistance_far": _cfd_level(above_wall[0] if above_wall else None, future, cfd),
        "resistance_main": resistance_main,
        "resistance_current": _cfd_level(resistance_current_fut, future, cfd),
        "support_current": _cfd_level(support_current_fut, future, cfd),
        "support_main": support_main,
        "support_deep": _cfd_level(below_wall[-1] if below_wall else None, future, cfd),
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
    for tf in ("m1", "m5", "m15"):
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
    """Build complete targets only from normalized QuikStrike strikes/gamma levels."""
    future = _num(parsed.get("future_price"))
    cfd = _num(parsed.get("cfd_price"))
    raw_rows = ((parsed.get("raw_series") or {}).get("gex") or {}).get("rows") or []
    strikes_futures = _unique_sorted([
        _num(row.get("strike"))
        for row in raw_rows
        if isinstance(row, dict) and _num(row.get("strike")) is not None
    ])
    strikes_cfd = [
        value for value in (_cfd_level(strike, future, cfd) for strike in strikes_futures)
        if value is not None
    ]
    long_entry = levels.get("resistance_current")
    short_entry = levels.get("support_current")
    structural = [
        _num(gamma.get("negative_zone")),
        _num(gamma.get("gamma_mean")),
        _num(gamma.get("positive_zone")),
    ]
    long_candidates = _unique_sorted([
        value for value in strikes_cfd + structural
        if value is not None and long_entry is not None and value > long_entry
    ])
    short_candidates = _unique_sorted([
        value for value in strikes_cfd + structural
        if value is not None and short_entry is not None and value < short_entry
    ], reverse=True)
    return {
        "long_trigger": long_entry,
        "long_stop": levels.get("support_current"),
        "long_tp1": long_candidates[0] if len(long_candidates) > 0 else None,
        "long_tp2": long_candidates[1] if len(long_candidates) > 1 else None,
        "long_tp3": long_candidates[2] if len(long_candidates) > 2 else None,
        "short_trigger": short_entry,
        "short_stop": levels.get("resistance_current"),
        "short_tp1": short_candidates[0] if len(short_candidates) > 0 else None,
        "short_tp2": short_candidates[1] if len(short_candidates) > 1 else None,
        "short_tp3": short_candidates[2] if len(short_candidates) > 2 else None,
    }


def _valid_trade_ladder(plan: dict[str, Any]) -> bool:
    """Require strict directional ordering before a plan can reach delivery."""
    values = [
        _num(plan.get("long_stop")), _num(plan.get("long_trigger")),
        _num(plan.get("long_tp1")), _num(plan.get("long_tp2")), _num(plan.get("long_tp3")),
        _num(plan.get("short_tp3")), _num(plan.get("short_tp2")),
        _num(plan.get("short_tp1")), _num(plan.get("short_trigger")), _num(plan.get("short_stop")),
    ]
    if any(value is None for value in values):
        return False
    (long_stop, long_trigger, long_tp1, long_tp2, long_tp3,
     short_tp3, short_tp2, short_tp1, short_trigger, short_stop) = values
    return (long_stop < long_trigger < long_tp1 < long_tp2 < long_tp3
            and short_tp3 < short_tp2 < short_tp1 < short_trigger < short_stop)


def _validate_or_clear_trade_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Never allow a semantically inverted ladder into Telegram/LINE."""
    if _valid_trade_ladder(plan):
        return plan
    return {
        **plan,
        "long_trigger": None, "long_stop": None,
        "long_tp1": None, "long_tp2": None, "long_tp3": None,
        "short_trigger": None, "short_stop": None,
        "short_tp1": None, "short_tp2": None, "short_tp3": None,
        "status": "NO_TRADE", "direction": "WAIT",
    }


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
    deterministic = _deterministic_trade_levels(parsed, levels, gamma)
    plan = {
        "long": {"entry": deterministic["long_trigger"], "stop": deterministic["long_stop"],
                 "tp1": deterministic["long_tp1"], "tp2": deterministic["long_tp2"], "tp3": deterministic["long_tp3"]},
        "short": {"entry": deterministic["short_trigger"], "stop": deterministic["short_stop"],
                  "tp1": deterministic["short_tp1"], "tp2": deterministic["short_tp2"], "tp3": deterministic["short_tp3"]},
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
    if bias not in {"BUY", "SELL"}:
        bias = "WAIT"

    def plan_line(side: str, values: dict[str, float | None]) -> str:
        rr = long_rr if side == "LONG" else short_rr
        return (
            f"{side} Entry {_fmt(values['entry'])} | Stop {_fmt(values['stop'])} | "
            f"TP1 {_fmt(values['tp1'])} | TP2 {_fmt(values['tp2'])} | "
            f"RR1 {_fmt(rr[0])}R | RR2 {_fmt(rr[1])}R"
        )

    ai["trade_plan"] = {
        "status": "CONDITIONAL",
        "direction": bias if bias in {"BUY", "SELL"} and has_any_numeric_plan else "WAIT",
        "long_trigger": deterministic["long_trigger"], "long_stop": deterministic["long_stop"],
        "long_tp1": deterministic["long_tp1"], "long_tp2": deterministic["long_tp2"], "long_tp3": deterministic["long_tp3"],
        "short_trigger": deterministic["short_trigger"], "short_stop": deterministic["short_stop"],
        "short_tp1": deterministic["short_tp1"], "short_tp2": deterministic["short_tp2"], "short_tp3": deterministic["short_tp3"],
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

    ai["scenarios"] = {
        "bull": f"ยืนเหนือ {_fmt(plan['long']['entry'])} และ hold/retest ได้ → TP1 {_fmt(plan['long']['tp1'])} → TP2 {_fmt(plan['long']['tp2'])} → TP3 {_fmt(plan['long']['tp3'])}; invalidation ใต้ {_fmt(plan['long']['stop'])}",
        "bear": f"หลุด {_fmt(plan['short']['entry'])} และ failed retest → TP1 {_fmt(plan['short']['tp1'])} → TP2 {_fmt(plan['short']['tp2'])} → TP3 {_fmt(plan['short']['tp3'])}; invalidation เหนือ {_fmt(plan['short']['stop'])}",
        "sideway": f"ราคาอยู่ระหว่าง {_fmt(plan['short']['entry'])} และ {_fmt(plan['long']['entry'])} โดยยังไม่มี breakout confirmation ให้มองเป็น range",
    }

    ai["market_state"] = state
    return ai
