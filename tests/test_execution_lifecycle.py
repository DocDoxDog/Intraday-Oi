from src.execution_lifecycle import arm_paper_order, fill_paper_order
from src.paper_execution import Quote


def test_paper_order_requires_both_execution_and_risk_gate():
    bad = arm_paper_order(
        {"execution_ready": True, "risk": {"status": "NO_TRADE"}},
        symbol="XAUUSD",
        order_id="1",
        quantity=0.1,
        submitted_at="2026-11-20T10:00:00Z",
    )
    assert bad.status == "REJECTED"


def test_paper_order_can_fill_when_gates_pass():
    route = {
        "execution_ready": True,
        "risk": {"status": "PASS"},
        "side": "LONG",
        "entry_reference": 3980.0,
        "stop": 3977.0,
        "targets": [3986.0],
    }
    armed = arm_paper_order(
        route,
        symbol="XAUUSD",
        order_id="2",
        quantity=0.1,
        submitted_at="2026-11-20T10:00:00Z",
    )
    assert armed.status == "ARMED"
    result = fill_paper_order(
        armed.order,
        Quote("2026-11-20T10:00:00Z", 3979.9, 3980.1),
    )
    assert result["fill_price"] >= 3980.1
