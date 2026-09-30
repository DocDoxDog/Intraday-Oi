from intelligence.commercial_metrics import UnitEconomics, arpu, mrr


def test_unit_economics_margin_is_transparent():
    economics = UnitEconomics(1000, 30, 100, 50, 100, 20, 80, 10, 60)
    assert economics.gross_profit == 550
    assert economics.gross_margin == 0.55


def test_arpu_and_mrr_are_zero_safe():
    assert arpu(100, 0) == 0.0
    assert arpu(100, 4) == 25.0
    assert mrr(-1) == 0.0