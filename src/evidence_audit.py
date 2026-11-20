"""Statistical evidence and promotion gates for Intraday-Oi.

This module is intentionally dependency-light and deterministic. It does not
create alpha; it prevents optimistic reporting and turns research outputs into
an auditable evidence ladder.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import log, sqrt
from statistics import NormalDist
from typing import Any, Iterable, Sequence

_NORM = NormalDist()


def _clean(xs: Iterable[float]) -> list[float]:
    out: list[float] = []
    for x in xs:
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if v == v and v not in (float("inf"), float("-inf")):
            out.append(v)
    return out


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials <= 0:
        return (float("nan"), float("nan"))
    successes = max(0, min(int(successes), int(trials)))
    p = successes / trials
    z = _NORM.inv_cdf((1.0 + confidence) / 2.0)
    denom = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denom
    radius = z * sqrt((p * (1.0 - p) / trials) + z * z / (4.0 * trials * trials)) / denom
    return (max(0.0, center - radius), min(1.0, center + radius))


def mean_ci(values: Sequence[float], confidence: float = 0.95) -> tuple[float, float]:
    xs = _clean(values)
    n = len(xs)
    if n == 0:
        return (float("nan"), float("nan"))
    mean = sum(xs) / n
    if n == 1:
        return (mean, mean)
    variance = sum((x - mean) ** 2 for x in xs) / (n - 1)
    se = sqrt(variance / n)
    z = _NORM.inv_cdf((1.0 + confidence) / 2.0)
    return (mean - z * se, mean + z * se)


def bootstrap_mean_ci(
    values: Sequence[float],
    confidence: float = 0.95,
    iterations: int = 4000,
    seed: int = 1729,
) -> tuple[float, float]:
    """Deterministic percentile bootstrap CI for the sample mean."""
    xs = _clean(values)
    n = len(xs)
    if not xs:
        return (float("nan"), float("nan"))
    if n == 1:
        return (xs[0], xs[0])
    state = int(seed) & 0xFFFFFFFF
    samples: list[float] = []
    for _ in range(max(100, int(iterations))):
        total = 0.0
        for _ in range(n):
            state ^= (state << 13) & 0xFFFFFFFF
            state ^= (state >> 17)
            state ^= (state << 5) & 0xFFFFFFFF
            total += xs[state % n]
        samples.append(total / n)
    samples.sort()
    alpha = (1.0 - confidence) / 2.0
    lo = samples[int(alpha * (len(samples) - 1))]
    hi = samples[int((1.0 - alpha) * (len(samples) - 1))]
    return (lo, hi)


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Return FDR-adjusted q-values in original order."""
    ranked = []
    for i, p in enumerate(p_values):
        try:
            v = min(1.0, max(0.0, float(p)))
        except (TypeError, ValueError):
            v = 1.0
        ranked.append((i, v))
    ranked.sort(key=lambda x: x[1])
    m = max(1, len(ranked))
    adjusted = [1.0] * len(ranked)
    running = 1.0
    for rank in range(len(ranked), 0, -1):
        idx, p = ranked[rank - 1]
        value = min(running, p * m / rank)
        running = value
        adjusted[idx] = value
    return adjusted


def _skewness(xs: Sequence[float]) -> float:
    if len(xs) < 3:
        return 0.0
    mean = sum(xs) / len(xs)
    m2 = sum((x - mean) ** 2 for x in xs) / len(xs)
    if m2 <= 0:
        return 0.0
    m3 = sum((x - mean) ** 3 for x in xs) / len(xs)
    return m3 / (m2 ** 1.5)


def _excess_kurtosis(xs: Sequence[float]) -> float:
    if len(xs) < 4:
        return 0.0
    mean = sum(xs) / len(xs)
    m2 = sum((x - mean) ** 2 for x in xs) / len(xs)
    if m2 <= 0:
        return 0.0
    m4 = sum((x - mean) ** 4 for x in xs) / len(xs)
    return m4 / (m2 * m2) - 3.0


def sharpe_ratio(returns: Sequence[float], annualization: float = 1.0) -> float | None:
    xs = _clean(returns)
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    variance = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    if variance <= 0:
        return None
    return mean / sqrt(variance) * sqrt(max(0.0, annualization))


def probabilistic_sharpe_ratio(
    returns: Sequence[float],
    benchmark_sr: float = 0.0,
    annualization: float = 1.0,
) -> float | None:
    xs = _clean(returns)
    n = len(xs)
    sr = sharpe_ratio(xs, annualization=annualization)
    if sr is None or n < 3:
        return None
    skew = _skewness(xs)
    kurt = _excess_kurtosis(xs)
    denom = sqrt(max(1e-12, (1.0 - skew * sr + ((kurt + 3.0) / 4.0) * sr * sr) / (n - 1)))
    z = (sr - benchmark_sr) / denom
    return _NORM.cdf(z)


def deflated_sharpe_ratio(
    returns: Sequence[float],
    trials: int,
    annualization: float = 1.0,
) -> float | None:
    """Approximate DSR against the best of N strategy trials."""
    xs = _clean(returns)
    sr = sharpe_ratio(xs, annualization=annualization)
    n = len(xs)
    if sr is None or n < 3 or trials < 1:
        return None
    expected_max_z = _NORM.inv_cdf((trials - 0.375) / (trials + 0.25))
    benchmark = expected_max_z / sqrt(max(1.0, n))
    return probabilistic_sharpe_ratio(xs, benchmark_sr=benchmark, annualization=annualization)


def profit_factor(r_multiples: Sequence[float]) -> float | None:
    xs = _clean(r_multiples)
    gains = sum(x for x in xs if x > 0)
    losses = -sum(x for x in xs if x < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else None
    return gains / losses


def event_bootstrap_test(
    returns: Sequence[float],
    null_value: float = 0.0,
    iterations: int = 4000,
    seed: int = 2718,
) -> dict[str, Any]:
    """Bootstrap p-value for mean return against a fixed null."""
    xs = _clean(returns)
    if not xs:
        return {"n": 0, "mean": None, "p_value": None}
    observed = sum(xs) / len(xs)
    centered = [x - observed + null_value for x in xs]
    state = int(seed) & 0xFFFFFFFF
    exceed = 0
    n = len(xs)
    iters = max(100, int(iterations))
    for _ in range(iters):
        total = 0.0
        for _ in range(n):
            state ^= (state << 13) & 0xFFFFFFFF
            state ^= (state >> 17)
            state ^= (state << 5) & 0xFFFFFFFF
            total += centered[state % n]
        sample = total / n
        if abs(sample - null_value) >= abs(observed - null_value):
            exceed += 1
    p = (exceed + 1) / (iters + 1)
    lo, hi = bootstrap_mean_ci(xs)
    return {"n": n, "mean": observed, "ci95": [lo, hi], "p_value": p}


def _combinations(values: Sequence[int], k: int):
    if k == 0:
        yield tuple()
        return
    if len(values) < k:
        return
    for i in range(len(values) - k + 1):
        for tail in _combinations(values[i + 1 :], k - 1):
            yield (values[i],) + tail


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def cscv_pbo(strategy_returns: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Combinatorial Symmetric Cross-Validation style PBO estimate.

    Rows are strategy trials; columns are ordered time blocks. For each
    half-split, the best in-sample strategy is scored out of sample.
    """
    matrix = [list(map(float, row)) for row in strategy_returns if row]
    if len(matrix) < 2:
        return {"splits": 0, "pbo": None}
    blocks = len(matrix[0])
    if blocks < 4 or any(len(row) != blocks for row in matrix):
        return {"splits": 0, "pbo": None, "reason": "rectangular matrix with >=4 blocks required"}
    half = blocks // 2
    combinations = list(_combinations(range(blocks), half))
    if len(combinations) > 256:
        combinations = combinations[:256]
    bad = 0
    logits: list[float] = []
    for is_idx in combinations:
        is_set = set(is_idx)
        oos_idx = [i for i in range(blocks) if i not in is_set]
        scores_in = [sum(row[i] for i in is_idx) for row in matrix]
        best = max(range(len(matrix)), key=lambda i: scores_in[i])
        oos_scores = [sum(row[i] for i in oos_idx) for row in matrix]
        rank = sum(v < oos_scores[best] for v in oos_scores) / max(1, len(oos_scores) - 1)
        rank = min(max(rank, 1e-6), 1.0 - 1e-6)
        logits.append(log(rank / (1.0 - rank)))
        if rank < 0.5:
            bad += 1
    total = len(combinations)
    return {
        "splits": total,
        "pbo": bad / total if total else None,
        "median_logit": _median(logits),
    }


@dataclass(frozen=True)
class PromotionPolicy:
    min_trades_oos: int = 100
    min_oos_months: int = 3
    max_pbo: float = 0.50
    min_psr: float = 0.95
    min_dsr: float = 0.90
    min_pf: float = 1.15
    max_drawdown_r: float = 5.0
    max_cost_degradation_r: float = 0.15
    require_live_for_live: bool = True
    min_live_trades: int = 100
    min_live_days: int = 30


def evaluate_promotion(
    *,
    oos_returns_r: Sequence[float],
    oos_months: int,
    pbo: float | None,
    max_drawdown_r: float | None,
    cost_degradation_r: float | None,
    live_trades: int = 0,
    live_days: int = 0,
    live_mode: bool = False,
    policy: PromotionPolicy | None = None,
) -> dict[str, Any]:
    """Return an evidence-level decision, never a future-profit claim."""
    policy = policy or PromotionPolicy()
    xs = _clean(oos_returns_r)
    wins = sum(x > 0 for x in xs)
    pf = profit_factor(xs)
    psr = probabilistic_sharpe_ratio(xs)
    dsr = deflated_sharpe_ratio(xs, trials=max(1, len(xs)))
    checks = {
        "min_trades_oos": len(xs) >= policy.min_trades_oos,
        "min_oos_months": oos_months >= policy.min_oos_months,
        "pbo": pbo is not None and pbo <= policy.max_pbo,
        "psr": psr is not None and psr >= policy.min_psr,
        "dsr": dsr is not None and dsr >= policy.min_dsr,
        "profit_factor": pf is not None and pf >= policy.min_pf,
        "drawdown": max_drawdown_r is not None and abs(max_drawdown_r) <= policy.max_drawdown_r,
        "cost_stress": cost_degradation_r is not None and cost_degradation_r <= policy.max_cost_degradation_r,
    }
    if policy.require_live_for_live:
        checks["live_evidence"] = live_trades >= policy.min_live_trades and live_days >= policy.min_live_days
    passed_research = all(checks[k] for k in checks if k != "live_evidence")
    passed_live = passed_research and checks.get("live_evidence", True)
    if live_mode and passed_live:
        stage = "LIVE_ELIGIBLE"
    elif passed_research:
        stage = "PAPER_ELIGIBLE"
    elif len(xs) > 0:
        stage = "RESEARCH_ONLY"
    else:
        stage = "DATA_INSUFFICIENT"
    return {
        "stage": stage,
        "n_oos": len(xs),
        "win_rate": wins / len(xs) if xs else None,
        "profit_factor": pf,
        "psr": psr,
        "dsr": dsr,
        "pbo": pbo,
        "checks": checks,
        "policy": asdict(policy),
        "warning": "Promotion status is not proof of future profitability.",
    }
