from src.evidence_audit import (
    wilson_interval, mean_ci, bootstrap_mean_ci, benjamini_hochberg,
    profit_factor, probabilistic_sharpe_ratio, deflated_sharpe_ratio,
    cscv_pbo, evaluate_promotion,
)


def test_wilson_and_fdr():
    lo, hi = wilson_interval(8, 10)
    assert 0 <= lo < hi <= 1
    q = benjamini_hochberg([0.01, 0.04, 0.2])
    assert q[0] <= q[1] <= q[2]


def test_bootstrap_is_deterministic():
    x = [1, 2, 3, 4, 5]
    assert bootstrap_mean_ci(x, iterations=500, seed=123) == bootstrap_mean_ci(x, iterations=500, seed=123)
    assert mean_ci(x)[0] < 3 < mean_ci(x)[1]


def test_effect_metrics():
    r = [0.5, -0.25, 0.8, -0.1, 0.3, 0.2]
    assert profit_factor(r) > 1
    assert probabilistic_sharpe_ratio(r) is not None
    assert deflated_sharpe_ratio(r, trials=10) is not None


def test_cscv_pbo():
    matrix = [
        [0.2, 0.2, 0.2, 0.2],
        [0.1, 0.1, 0.1, 0.1],
        [-0.1, -0.1, -0.1, -0.1],
    ]
    out = cscv_pbo(matrix)
    assert out["pbo"] == 0.0


def test_promotion_never_jumps_to_live_without_live_evidence():
    out = evaluate_promotion(
        oos_returns_r=[0.4] * 120,
        oos_months=6,
        pbo=0.1,
        max_drawdown_r=-2.0,
        cost_degradation_r=0.05,
        live_trades=0,
        live_days=0,
        live_mode=True,
    )
    assert out["stage"] != "LIVE_ELIGIBLE"
