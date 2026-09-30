from __future__ import annotations

from datetime import datetime, timezone

from quant.models import DataStatus, MarketState


def build_market_state(
    *,
    symbol: str,
    price: float | None,
    as_of: datetime,
    positioning: dict,
    iv: float | None = None,
    realized_vol: float | None = None,
    positioning_regime: str = "UNKNOWN",
    volatility_regime: str = "UNKNOWN",
    data_quality: float = 0.0,
    data_status: DataStatus = DataStatus.UNAVAILABLE,
    data_age_seconds: float | None = None,
    dataset_version: str = "unknown",
) -> MarketState:
    gex = positioning.get("gex") or {}
    dex = positioning.get("dex") or {}
    oi = positioning.get("oi") or {}

    calculation_version = str(
        gex.get("calculation_version")
        or "unknown"
    )
    assumptions = tuple(positioning.get("assumptions") or ())
    evidence = (
        f"GEX_STATUS:{gex.get('status', 'unavailable')}",
        f"DEX_STATUS:{dex.get('status', 'unavailable')}",
        f"OI_COUNT:{oi.get('count', 0)}",
    )

    return MarketState(
        symbol=symbol,
        price=price,
        as_of=as_of,
        oi=oi.get("total_oi"),
        oi_change=oi.get("oi_change_total"),
        gex=gex.get("net_gex"),
        dex=dex.get("net_dex"),
        iv=iv,
        realized_vol=realized_vol,
        gamma_flip=gex.get("gamma_flip"),
        call_wall=gex.get("call_wall"),
        put_wall=gex.get("put_wall"),
        positioning_regime=positioning_regime,
        volatility_regime=volatility_regime,
        data_quality=max(0.0, min(1.0, float(data_quality))),
        data_age_seconds=data_age_seconds,
        data_status=data_status,
        dataset_version=dataset_version,
        calculation_version=calculation_version,
        sign_convention=gex.get("gex_sign_convention"),
        gamma_source=(
            "MIXED_SOURCE_AND_DERIVED"
            if gex.get("source_gamma_count") and gex.get("derived_gamma_count")
            else "SOURCE_GAMMA"
            if gex.get("source_gamma_count")
            else "BLACK76_FROM_IV"
            if gex.get("derived_gamma_count")
            else None
        ),
        assumptions=assumptions,
        evidence=evidence,
    )
