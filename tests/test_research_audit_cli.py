from src.research_audit_cli import build_report


def test_cli_report_combines_pit_pbo_and_promotion_gate():
    report = build_report({
        "strategy_id": "demo",
        "strategy_version": "v1",
        "oos_months": 4,
        "trades_r": [0.25, -0.1, 0.3, 0.1] * 30,
        "max_drawdown_r": -2.0,
        "cost_degradation_r": 0.05,
        "pit_rows": [{
            "event_time": "2026-11-20T10:00:00Z",
            "as_of": "2026-11-20T10:00:00Z",
        }],
        "strategy_trials": [
            [0.25, 0.2, 0.3, 0.25],
            [0.1, 0.1, 0.1, 0.1],
            [-0.1, -0.1, -0.1, -0.1],
        ],
        "live_mode": True,
    })
    assert report["pit"]["status"] == "PASS"
    assert report["pbo_detail"]["splits"] > 0
    assert report["stage"] != "LIVE_ELIGIBLE"
