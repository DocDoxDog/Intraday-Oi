from __future__ import annotations

from datetime import datetime, timezone

from quant.exposure.dex import calculate_dex
from quant.exposure.gex import calculate_gex_result
from quant.oi.engine import aggregate_oi


def build_positioning_snapshot(
    *,
    symbol: str,
    price: float | None,
    rows,
    oi_observations=(),
    dte_days: float | None,
    multiplier: float,
    convention: str,
    dataset_version: str,
    as_of: datetime,
) -> dict:
    oi = aggregate_oi(oi_observations) if oi_observations else {
        "total_oi": sum(float(r.get("oiCall") or 0) + float(r.get("oiPut") or 0) for r in rows),
        "oi_change_total": None,
    }

    gex = calculate_gex_result(
        rows,
        price if price is not None else 0.0,
        dte_days=dte_days,
        multiplier=multiplier,
        convention=convention,
        underlying=symbol,
    )

    dex = calculate_dex(rows, multiplier=multiplier)

    return {
        "symbol": symbol,
        "as_of": as_of,
        "dataset_version": dataset_version,
        "price": price,
        "oi": oi,
        "gex": gex,
        "dex": dex,
        "positioning_regime": "UNKNOWN",
        "volatility_regime": "UNKNOWN",
        "assumptions": (
            "dealer_positioning_not_observed",
            f"gex_sign_convention={convention}",
        ),
    }
