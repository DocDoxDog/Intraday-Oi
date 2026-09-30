"""Transition adapter from the existing parser output to canonical MarketState.

This module intentionally does not calculate new OI/GEX math. It consumes the
canonical quant result already attached to raw_series and marks the state
INCOMPLETE while publication-time and canonical contract provenance are still
missing from the legacy QuikStrike snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quant.market_state import build_market_state
from quant.models import DataStatus
from quant.serialization import to_jsonable


def attach_market_state(parsed: dict[str, Any], *, dataset_version: str = "legacy-quikstrike-adapter-v1") -> dict[str, Any]:
    raw = parsed.setdefault("raw_series", {})
    gex = raw.get("gex") or {}
    totals = raw.get("totals") or {}
    delta = raw.get("delta_exposure") or {}

    # Legacy snapshots do not yet expose authoritative observation/publication
    # timestamps or a fully resolved contract ID. Do not manufacture them.
    positioning_payload = {
        "oi": {
            "count": len(raw.get("strike_rows") or []),
            "total_oi": totals.get("open_interest_total"),
            "oi_change_total": (
                totals.get("oi_delta_put", 0) + totals.get("oi_delta_call", 0)
                if totals.get("oi_delta_put") is not None
                and totals.get("oi_delta_call") is not None
                else None
            ),
        },
        "gex": gex,
        "dex": {
            "status": "ok" if delta else "unavailable",
            "net_dex": delta.get("net_delta_exposure"),
            "gross_dex": delta.get("gross_delta_exposure"),
        },
        "iv": parsed.get("vol"),
        "evidence": (
            "LEGACY_QUIKSTRIKE_SNAPSHOT",
            "PUBLIC_DEALER_SIGN_ASSUMPTION_NOT_OBSERVED",
        ),
    }

    state = build_market_state(
        symbol="GC",
        price=parsed.get("future_price"),
        as_of=datetime.now(timezone.utc),
        positioning={
            **positioning_payload,
            "assumptions": (
                "legacy_quikstrike_snapshot_adapter",
                "publication_time_unknown",
                "canonical_contract_id_unresolved",
            ),
        },
        iv=parsed.get("vol"),
        realized_vol=None,
        positioning_regime="UNKNOWN",
        volatility_regime="UNKNOWN",
        data_quality=0.0,
        data_status=DataStatus.INCOMPLETE,
        data_age_seconds=None,
        dataset_version=dataset_version,
    )

    serialized = to_jsonable(state)
    raw["market_state"] = serialized
    raw["market_state_positioning"] = to_jsonable(positioning_payload)
    parsed["market_state"] = serialized
    parsed["market_state_positioning"] = to_jsonable(positioning_payload)
    return parsed
