from src.history import _history_contract_prefix



def test_history_contract_prefix_stable():
    first = "Gold (OG|GC) OG1V6 (1.23 DTE) vs 4210.8 (+8.5) - Open Interest"
    second = "Gold (OG|GC) OG1V6 (0.21 DTE) vs 4208.5 (+6.9) - Open Interest"
    assert _history_contract_prefix(first) == "Gold (OG|GC) OG1V6"
    assert _history_contract_prefix(second) == "Gold (OG|GC) OG1V6"
