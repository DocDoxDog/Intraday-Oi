"""Evidence-first order-flow and microstructure feature extraction.

The module is source-agnostic. It never invents trades/book observations.
"""
from __future__ import annotations
from typing import Any

def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _classify_trade(t: dict[str, Any]) -> tuple[str | None, float | None]:
    side = str(t.get("aggressor_side") or t.get("side") or "").upper()
    price = _num(t.get("price"))
    bid = _num(t.get("bid"))
    ask = _num(t.get("ask"))
    if side in {"BUY", "B"}:
        return "BUY", price
    if side in {"SELL", "S"}:
        return "SELL", price
    if price is not None and ask is not None and price >= ask:
        return "BUY", price
    if price is not None and bid is not None and price <= bid:
        return "SELL", price
    return None, price

def _book_metrics(book: list[dict[str, Any]]) -> dict[str, Any]:
    if not book:
        return {"status": "UNKNOWN"}
    rows = [x for x in book if isinstance(x, dict)]
    bids = [_num(x.get("bid_size")) for x in rows]
    asks = [_num(x.get("ask_size")) for x in rows]
    bids = [x for x in bids if x is not None and x >= 0]
    asks = [x for x in asks if x is not None and x >= 0]
    bid = bids[0] if bids else None
    ask = asks[0] if asks else None
    denom = (bid + ask) if bid is not None and ask is not None else None
    imbalance = ((bid - ask) / denom) if denom else None
    bid_px = _num(rows[0].get("bid_price"))
    ask_px = _num(rows[0].get("ask_price"))
    spread = ask_px - bid_px if bid_px is not None and ask_px is not None else None
    return {"status": "OK", "best_bid_depth": bid, "best_ask_depth": ask,
            "imbalance": round(imbalance, 6) if imbalance is not None else None,
            "spread": round(spread, 6) if spread is not None else None}

def build_order_flow_context(trades: list[dict[str, Any]] | None = None,
                             book: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    trades = trades or []
    book = book or []
    classified = []
    for t in trades:
        if not isinstance(t, dict):
            continue
        side, price = _classify_trade(t)
        size = _num(t.get("size") if t.get("size") is not None else t.get("quantity"))
        if side and size is not None and size >= 0:
            classified.append((side, price, size))
    if not trades and not book:
        return {
            "version": "order-flow-v1", "status": "UNKNOWN",
            "availability": "NOT_PROVIDED", "source_fields_used": [],
            "aggression": {}, "book": {}, "hypotheses": [],
            "limitations": ["No tick trades or order-book observations were supplied."]
        }

    buy = sum(x[2] for x in classified if x[0] == "BUY")
    sell = sum(x[2] for x in classified if x[0] == "SELL")
    delta = buy - sell if classified else None
    prices = [x[1] for x in classified if x[1] is not None]
    displacement = (max(prices) - min(prices)) if len(prices) >= 2 else None
    total = buy + sell if classified else None
    hypotheses = []
    if classified and total and displacement is not None:
        # Candidate only: low displacement relative to heavy aggression.
        # The ratio is intentionally exposed as derived evidence, not a signal score.
        aggression_per_move = total / max(abs(displacement), 1e-9)
        if aggression_per_move > max(total, 1) / max(abs(displacement), 1e-9) * 0.8:
            hypotheses.append({
                "type": "ABSORPTION_CANDIDATE",
                "status": "CANDIDATE",
                "reason": "Aggressive classified volume coexists with limited observed price displacement.",
            })

    book_metrics = _book_metrics(book)
    return {
        "version": "order-flow-v1",
        "status": "OK" if classified or book_metrics.get("status") == "OK" else "UNKNOWN",
        "availability": "OBSERVED",
        "source_fields_used": sorted({
            key for t in trades if isinstance(t, dict) for key in t.keys()
            if key in {"aggressor_side","side","price","bid","ask","size","quantity"}
        }),
        "aggression": {
            "buy": buy if classified else None,
            "sell": sell if classified else None,
            "delta": delta,
            "trade_count": len(classified),
            "total": total,
            "price_displacement": displacement,
        },
        "book": book_metrics,
        "hypotheses": hypotheses,
        "limitations": [
            "Aggressor classification falls back to quote test only when bid/ask are supplied.",
            "Absorption is a hypothesis and requires event-study validation before production use.",
            "No MBO queue inference is made without queue/order identifiers.",
        ],
    }
