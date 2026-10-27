"""Deep cross-domain reasoning context for the Gold analyst."""
from __future__ import annotations
from typing import Any

def _d(v: Any) -> Any:
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _d(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_d(x) for x in v]
    return str(v)

def _pick(d: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: d.get(k) for k in keys if k in d}

def _compact_series(value: Any, limit: int = 12) -> Any:
    """Keep evidence shape while preventing long historical arrays from flooding the LLM."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k)
            if key in {"bars", "candles", "series", "points", "rows", "snapshots"} and isinstance(v, list):
                out[key] = [_d(x) for x in v[:limit]]
                if len(v) > limit:
                    out[f"{key}_count"] = len(v)
                continue
            out[key] = _compact_series(v, limit)
        return out
    if isinstance(value, list):
        if len(value) > limit:
            return [_compact_series(x, limit) for x in value[:limit]] + [{"_truncated_count": len(value) - limit}]
        return [_compact_series(x, limit) for x in value]
    return value

def _history_summary(history: dict[str, Any] | None) -> dict[str, Any]:
    history = history or {}
    out = {}
    for key in ("hour_ago", "two_hours_ago"):
        row = history.get(key)
        if isinstance(row, dict):
            raw = row.get("raw_series") or {}
            totals = raw.get("totals") or {}
            gex = raw.get("gex") or {}
            out[key] = {
                "captured_at": row.get("captured_at"),
                "future_price": row.get("future_price"),
                "future_chg": row.get("future_chg"),
                "vol": row.get("vol"),
                "vol_chg": row.get("vol_chg"),
                "oi": {
                    "put": totals.get("open_interest_view_put", totals.get("open_interest_put")),
                    "call": totals.get("open_interest_view_call", totals.get("open_interest_call")),
                    "total": totals.get("open_interest_view_total", totals.get("open_interest_total")),
                    "delta_put": totals.get("oi_delta_put"),
                    "delta_call": totals.get("oi_delta_call"),
                    "delta_total": totals.get("oi_delta_total"),
                },
                "gex": _pick(gex, "net_gex", "gamma_flip", "call_wall", "put_wall"),
            }
    for key in ("today", "yesterday"):
        row = history.get(key)
        if isinstance(row, dict):
            out[key] = {
                "count": row.get("count", 0),
                "future_price_open": row.get("future_price_open"),
                "future_price_last": row.get("future_price_last"),
                "vol_last": row.get("vol_last"),
                "oi_first": _d(row.get("oi_first") or {}),
                "oi_last": _d(row.get("oi_last") or {}),
            }
    if history.get("oi_baseline") is not None:
        out["oi_baseline"] = _d(history.get("oi_baseline"))
    return out

def build_deep_reasoning_context(parsed: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = parsed.get("raw_series") or {}
    state = raw.get("market_state") or {}
    decision = state.get("decision") or {}
    gamma = raw.get("gex") or {}
    totals = raw.get("totals") or {}
    technical = parsed.get("technical_context") or {}
    volatility = state.get("volatility") or {}
    macro = raw.get("macro_state") or {}
    flow = raw.get("market_flow") or {}
    multi = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    rollover = raw.get("expiry_rollover") or {}
    historical = raw.get("historical_memory") or raw.get("multi_timeframe_memory") or {}
    return _d({
        "as_of": parsed.get("observed_at") or parsed.get("retrieved_at"),
        "market": _pick(parsed, "product_symbol", "contract", "cfd_price", "future_price", "spot_price", "basis_diff", "basis", "future_chg", "dte", "vol", "vol_chg"),
        "structure": {
            "regime": state.get("regime") or {},
            "decision": decision,
            "path": state.get("path") or flow.get("path") or {},
            "levels": state.get("levels") or {},
            "market_flow": _pick(flow, "status", "market_read", "flow_read", "nodes", "path"),
            "price_memory": flow.get("price_memory") or state.get("price_memory") or {},
        },
        "technical": _compact_series(technical),
        "options": {
            "totals": totals,
            "gex": _pick(gamma, "status", "net_gex", "call_gex_total", "put_gex_total", "gamma_flip", "call_wall", "put_wall", "max_abs_gex_strike", "gex_unit", "gamma_source"),
            "multi_expiry": {
                "status": multi.get("status"),
                "expiration_count": multi.get("expiration_count"),
                "columns": [
                    _pick(c, "code", "dte", "status", "observed_at")
                    for c in (multi.get("columns") or [])[:16]
                    if isinstance(c, dict)
                ],
                "zones": zones,
                "totals": multi.get("totals") or {},
            },
            "expiry_rollover": rollover,
            "oi_intelligence": {
                "delta_exposure": raw.get("delta_exposure") or {},
                "flow_hypotheses": raw.get("flow_hypotheses") or {},
                "oi_migration": raw.get("oi_migration") or {},
                "history_comparison": raw.get("history_comparison") or {},
            },
        },
        "volatility": {
            "current_iv": parsed.get("vol", parsed.get("iv")),
            "iv_change": parsed.get("vol_chg"),
            **_compact_series(volatility),
        },
        "quant": _compact_series(raw.get("quant_metrics") or parsed.get("quant_metrics") or {}),
        "macro": _compact_series(macro),
        "news": _compact_series(parsed.get("news_context") or {}, limit=8),
        "history": _history_summary(history),
        "historical_memory": _compact_series(historical, limit=12),
        "conflicts": _d(decision.get("conflicts") or []),
        "data_quality": {
            "analysis_status": state.get("analysis_status"),
            "evidence_completeness": state.get("evidence_completeness"),
            "limitations": parsed.get("data_limitations") or [],
        },
    })

__all__ = ["build_deep_reasoning_context"]
