from src.paper_execution import Quote, PaperOrder, simulate_fill, evaluate_fill_quality


def test_buy_crosses_ask_and_cost_is_measured():
    quote = Quote("2026-11-20T10:00:00Z", 3979.9, 3980.1)
    order = PaperOrder("o1", "XAUUSD", "BUY", 0.1, quote.timestamp, 3980.0)
    fill = simulate_fill(order, quote, latency_ms=200, extra_slippage_ticks=1, tick_size=0.01)
    assert fill.fill_price >= quote.ask
    q = evaluate_fill_quality(fill, tick_size=0.01)
    assert q["total_execution_cost"] > 0
