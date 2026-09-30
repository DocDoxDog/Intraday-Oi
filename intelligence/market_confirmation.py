from __future__ import annotations

from numbers import Number

from intelligence.news.models import MarketConfirmation


def confirm_market_reaction(
    *,
    price_reaction: Number | None,
    volatility_reaction: Number | None,
    oi_change: Number | None,
    gex_change: Number | None,
    dex_change: Number | None,
    market_state_changed: bool,
) -> MarketConfirmation:
    observed = [
        x for x in (
            price_reaction,
            volatility_reaction,
            oi_change,
            gex_change,
            dex_change,
        )
        if x is not None
    ]
    magnitudes = [min(abs(float(x)), 1.0) for x in observed]
    score = sum(magnitudes) / len(magnitudes) if magnitudes else 0.0
    if market_state_changed:
        score = min(1.0, 0.7 * score + 0.3)
    evidence = tuple(
        label for label, value in (
            ("price_reaction_observed", price_reaction),
            ("volatility_reaction_observed", volatility_reaction),
            ("oi_change_observed", oi_change),
            ("gex_change_observed", gex_change),
            ("dex_change_observed", dex_change),
            ("market_state_changed", market_state_changed),
        )
        if value is not None
    )
    return MarketConfirmation(
        confirmed=score >= 0.50,
        score=score,
        price_reaction=None if price_reaction is None else float(price_reaction),
        volatility_reaction=None if volatility_reaction is None else float(volatility_reaction),
        oi_change=None if oi_change is None else float(oi_change),
        gex_change=None if gex_change is None else float(gex_change),
        dex_change=None if dex_change is None else float(dex_change),
        market_state_changed=market_state_changed,
        evidence=evidence,
    )
