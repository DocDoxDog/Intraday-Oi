from __future__ import annotations

from typing import Any


def build_analysis_context(
    *,
    market_state: Any,
    news: list[dict[str, Any]],
    historical_state: list[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Build an evidence-only context package for an external LLM."""
    state = {
        "symbol": market_state.symbol,
        "price": market_state.price,
        "oi": market_state.oi,
        "oi_change": market_state.oi_change,
        "gex": market_state.gex,
        "dex": market_state.dex,
        "iv": market_state.iv,
        "realized_vol": market_state.realized_vol,
        "gamma_flip": market_state.gamma_flip,
        "call_wall": market_state.call_wall,
        "put_wall": market_state.put_wall,
        "positioning_regime": market_state.positioning_regime,
        "volatility_regime": market_state.volatility_regime,
        "data_status": market_state.data_status.value
            if hasattr(market_state.data_status, "value")
            else market_state.data_status,
        "data_quality": market_state.data_quality,
        "data_age_seconds": market_state.data_age_seconds,
        "as_of": market_state.as_of.isoformat(),
        "dataset_version": market_state.dataset_version,
        "calculation_version": market_state.calculation_version,
        "sign_convention": market_state.sign_convention,
        "gamma_source": market_state.gamma_source,
        "assumptions": list(market_state.assumptions),
        "evidence": list(market_state.evidence),
    }
    return {
        "market_state": state,
        "news": list(news),
        "historical_state": list(historical_state),
        "constraints": (
            "Use only supplied facts.",
            "Every numeric level must originate in market_state.",
            "Every news claim must retain its source URL and published time.",
            "Do not infer dealer inventory from public OI without an explicit assumption.",
            "Do not guarantee outcomes or returns.",
        ),
    }
