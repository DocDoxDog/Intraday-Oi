"""Compatibility wrapper for the canonical GEX engine.

The implementation now lives in quant.exposure.gex. This module preserves the
legacy import path during the dual-run migration window.
"""

from quant.exposure.gex import (
    GEX_CALCULATION_VERSION,
    black76_gamma,
    calculate_gex,
)


def enrich_raw_series(raw_series, future_price):
    result = calculate_gex(
        raw_series.get("strike_rows") or [],
        future_price,
        dte_days=raw_series.get("dte"),
    )
    raw_series["gex"] = result
    if result.get("status") == "ok":
        by_strike = {row["strike"]: row for row in result["rows"]}
        for row in raw_series.get("strike_rows") or []:
            match = by_strike.get(row.get("strike"))
            if match:
                row.update(
                    {
                        key: match[key]
                        for key in (
                            "call_gex",
                            "put_gex",
                            "net_gex",
                            "cumulative_gex",
                            "gamma_source",
                            "gex_sign_convention",
                            "gex_calculation_version",
                        )
                    }
                )
    return raw_series


__all__ = ["GEX_CALCULATION_VERSION", "black76_gamma", "calculate_gex", "enrich_raw_series"]
