from __future__ import annotations

from typing import Any


def build_daily_report(
    *,
    market_state,
    news_rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
) -> str:
    status = (
        market_state.data_status.value
        if hasattr(market_state.data_status, "value")
        else market_state.data_status
    )
    lines = [
        f"{market_state.symbol} DAILY MARKET REPORT",
        "",
        "WHAT CHANGED",
        f"Price: {market_state.price}",
        f"OI / ΔOI: {market_state.oi} / {market_state.oi_change}",
        f"GEX / DEX: {market_state.gex} / {market_state.dex}",
        f"IV / RV: {market_state.iv} / {market_state.realized_vol}",
        f"Regime: {market_state.positioning_regime} / {market_state.volatility_regime}",
        "",
        "MAJOR NEWS",
    ]
    lines.extend(
        f"{row.get('severity', 'MEDIUM')} | {row.get('headline', 'N/A')} | {row.get('source', 'UNKNOWN')}"
        for row in news_rows[:10]
    )
    if not news_rows:
        lines.append("No verified news available.")

    lines.extend(["", "SCENARIOS"])
    lines.extend(
        f"{row.get('scenario_id', 'UNKNOWN')} | {row.get('status', 'UNKNOWN')} | confidence={row.get('confidence', 0)}"
        for row in plan_rows[:5]
    )
    if not plan_rows:
        lines.append("No verified scenario plan available.")

    lines.extend([
        "",
        "DATA QUALITY",
        f"status={status}",
        f"quality={market_state.data_quality:.3f}",
        f"age={market_state.data_age_seconds}",
        f"dataset={market_state.dataset_version}",
        f"calculation={market_state.calculation_version}",
    ])
    return "\n".join(lines)
