"""Canonical options-intelligence contract.

This module is the boundary between QuikStrike/raw ingestion and downstream
consumers such as AI-Trader. It never invents market data and never turns
missing/stale observations into zeros.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

CANONICAL_VERSION = "canonical-options-v1"
GEX_MODEL = "dealer_short_all"
GEX_MODEL_VERSION = "canonical-gex-v2"


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def freshness_status(as_of: Any, now: datetime | None = None, max_age_seconds: int | None = None) -> str:
    if as_of is None:
        return "UNKNOWN"
    dt = _parse_ts(as_of)
    if dt is None:
        return "UNKNOWN"
    if max_age_seconds is None:
        return "VALID"
    now = now or datetime.now(timezone.utc)
    age = (now - dt).total_seconds()
    if age < 0:
        return "INVALID"
    return "VALID" if age <= max_age_seconds else "STALE"


def expiry_weight(dte_days: Any) -> float | None:
    """Deterministic display/aggregation weight, not a price forecast.

    Near-expiry gamma becomes more sensitive. The weight is deliberately
    bounded and monotonically increasing as DTE approaches zero.
    """
    dte = _num(dte_days)
    if dte is None or dte <= 0:
        return None
    return min(1.0, 1.0 / max(1.0, dte) ** 0.5)


def build_canonical_snapshot(
    snapshot: dict[str, Any],
    *,
    source: str = "quikstrike",
    quote_max_age_seconds: int = 300,
    iv_max_age_seconds: int = 21600,
    oi_max_age_seconds: int = 172800,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise TypeError("OPTIONS_SNAPSHOT_MUST_BE_DICT")

    raw = snapshot.get("raw_series") or {}
    gex = raw.get("gex") or {}
    selection = raw.get("expiration_selection") or {}
    observed_at = snapshot.get("observed_at") or snapshot.get("retrieved_at")

    oi_as_of = snapshot.get("oi_as_of") or raw.get("oi_as_of") or observed_at
    iv_as_of = snapshot.get("iv_as_of") or raw.get("iv_as_of") or observed_at
    quote_as_of = snapshot.get("quote_as_of") or raw.get("quote_as_of") or observed_at
    dte = _num(snapshot.get("dte"))
    if dte is None:
        dte = _num(raw.get("dte"))

    rows = []
    for source_row in raw.get("strike_rows") or []:
        if not isinstance(source_row, dict):
            continue
        strike = _num(source_row.get("strike"))
        if strike is None:
            continue
        rows.append({
            "strike": strike,
            "call_oi": _num(source_row.get("oiCall")),
            "put_oi": _num(source_row.get("oiPut")),
            "delta_oi_call": _num(source_row.get("oi_delta_call")),
            "delta_oi_put": _num(source_row.get("oi_delta_put")),
            "iv": _num(source_row.get("vol")),
            "call_delta": _num(source_row.get("callDelta")),
            "put_delta": _num(source_row.get("putDelta")),
            "gamma": _num(source_row.get("gamma")),
            "call_gex": _num(source_row.get("call_gex")),
            "put_gex": _num(source_row.get("put_gex")),
            "net_gex": _num(source_row.get("net_gex")),
        })

    return {
        "contract_version": CANONICAL_VERSION,
        "symbol": snapshot.get("contract") or "GC",
        "underlying_type": "futures",
        "source": source,
        "observed_at": observed_at,
        "expiration": {
            "code": snapshot.get("expiration_code") or selection.get("selected") or raw.get("expiration_code"),
            "dte_days": dte,
            "expires_at": snapshot.get("expires_at") or raw.get("expires_at"),
            "expiry_weight": expiry_weight(dte),
        },
        "freshness": {
            "oi": {"as_of": oi_as_of, "status": freshness_status(oi_as_of, max_age_seconds=oi_max_age_seconds)},
            "iv": {"as_of": iv_as_of, "status": freshness_status(iv_as_of, max_age_seconds=iv_max_age_seconds)},
            "quote": {"as_of": quote_as_of, "status": freshness_status(quote_as_of, max_age_seconds=quote_max_age_seconds)},
        },
        "gex": {
            "status": gex.get("status", "UNKNOWN"),
            "model": gex.get("model", GEX_MODEL),
            "model_version": gex.get("model_version", GEX_MODEL_VERSION),
            "convention": gex.get("convention", "dealer_call_positive_put_negative"),
            "unit": gex.get("gex_unit", "USD per 1% underlying move"),
            "net_gex": _num(gex.get("net_gex")),
            "gamma_flip": _num(gex.get("gamma_flip")),
            "call_wall": _num(gex.get("call_wall")),
            "put_wall": _num(gex.get("put_wall")),
            "source_gamma_count": gex.get("source_gamma_count"),
            "derived_gamma_count": gex.get("derived_gamma_count"),
        },
        "levels": rows,
        "data_quality": {
            "has_oi": any(r["call_oi"] is not None or r["put_oi"] is not None for r in rows),
            "has_delta_oi": any(r["delta_oi_call"] is not None or r["delta_oi_put"] is not None for r in rows),
            "has_iv": any(r["iv"] is not None for r in rows),
            "has_gex": any(r["net_gex"] is not None for r in rows),
        },
    }


def validate_canonical_snapshot(state: dict[str, Any]) -> list[str]:
    errors = []
    if state.get("contract_version") != CANONICAL_VERSION:
        errors.append("INVALID_CONTRACT_VERSION")
    if not state.get("symbol"):
        errors.append("MISSING_SYMBOL")
    if not state.get("source"):
        errors.append("MISSING_SOURCE")
    freshness = state.get("freshness") or {}
    for key in ("oi", "iv", "quote"):
        if key not in freshness:
            errors.append(f"MISSING_FRESHNESS_{key.upper()}")
    gex = state.get("gex") or {}
    if gex.get("status") == "ok" and not gex.get("model_version"):
        errors.append("MISSING_GEX_MODEL_VERSION")
    return errors
