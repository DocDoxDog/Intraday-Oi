from __future__ import annotations

from typing import Any


def build_morning_brief(
    *,
    market_rows: list[dict[str, Any]],
    news_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    max_news: int = 5,
    max_events: int = 5,
) -> str:
    """Compact, evidence-first brief. It never invents absent values."""
    lines = ["MORNING MARKET BRIEF", "", "MARKETS"]
    for row in market_rows[:10]:
        lines.append(
            f"{row.get('symbol', 'UNKNOWN')}: "
            f"price={row.get('price', 'N/A')} "
            f"regime={row.get('positioning_regime', 'UNKNOWN')} "
            f"GEX={row.get('gex', 'N/A')} "
            f"OI={row.get('oi', 'N/A')}"
        )

    lines.extend(["", "NEWS"])
    if news_rows:
        for row in news_rows[:max_news]:
            lines.append(
                f"{row.get('severity', 'MEDIUM')} | "
                f"{row.get('headline', 'N/A')} | "
                f"{row.get('source', 'UNKNOWN')} | "
                f"{row.get('url', '')}"
            )
    else:
        lines.append("No verified news items available.")

    lines.extend(["", "OI / GEX / VOLATILITY"])
    if market_rows:
        lines.append("Use the MarketState evidence panel for full levels and timestamps.")
    else:
        lines.append("No verified MarketState available.")

    lines.extend(["", "EVENTS TODAY"])
    if event_rows:
        for event in event_rows[:max_events]:
            lines.append(str(event.get("summary") or event.get("title") or "UNSPECIFIED EVENT"))
    else:
        lines.append("No verified events attached.")

    return "\n".join(lines)
