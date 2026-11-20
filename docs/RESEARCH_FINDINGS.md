# Intraday-OI Research Findings

Preliminary internal research. Not a performance guarantee.

| Hypothesis | Evidence | Status |
|---|---|---|
| Negative Gamma amplifies accepted moves | Event study + preliminary OOS | PROMISING |
| Gamma Wall Break + Acceptance | Event study | PROMISING |
| Negative Gamma + downside break | Event study | PROMISING |
| H1 3SD continuation | Backtest + preliminary OOS | PROMISING / RECHECK |
| Countertrend after extreme 3SD | Backtest | WEAK |
| OI Barrier Flow + Price Response | Small OOS | PROMISING / SMALL SAMPLE |
| Next Gamma Wall as TP | Tiny OOS | INSUFFICIENT |
| Basis as directional signal | Small sample | NOT VALIDATED |
| IV/DTE as standalone direction | Not supported | REJECT |
| IV/DTE as urgency context | Preliminary | PROMISING |

## Existing observations

Negative Gamma:
~369 snapshots; 30m ~-0.027%, 60m ~-0.030%, 120m ~-0.030%.
Negative Gamma + H1 bearish: ~253 observations; 60m short hit ~58.7%.
Negative Gamma + H1 bearish + bullish regular divergence: ~38-40 observations; 60m short hit ~68.4%.

Gamma Wall break:
Upside: 26 events; 30m ~+0.307%, 60m ~+0.320%, 120m ~+0.388%.
Downside: 39 events; 30m ~+0.308%, 60m ~+0.312%, 120m ~+0.378%.

Break + Acceptance:
Upside: 17 events; 30m ~+0.375%, 60m ~+0.476%, 120m ~+0.578%.
Downside: 27 events; 30m ~+0.284%, 60m ~+0.382%, 120m ~+0.464%.

3SD:
~484 combined CFD events, 1 ATR stop, 1.5 ATR target, max hold 12h, average ~+0.226R/trade, PF ~1.47.
A 0.2R cost stress reduced aggregate edge to roughly +0.026R. Execution cost can consume most of apparent edge.

OI Barrier Flow:
Preliminary OOS directional hit ~79.2% on ~24 events in the tested alignment.
First-touch trade-style test: 13 trades, 6 TP, 6 SL, 1 no-touch.
Useful hypothesis, insufficient profitability evidence.

Gamma Wall target:
Tiny OOS: 4 TP, 1 SL, 1 no-touch, TP-first ~80%, average target/R ~0.38R, average realized ~+0.095R.
Interesting but insufficient.

Basis:
Within H1 bearish + Negative Gamma + Z<=-2:
basis decreasing: 10 events, avg short return ~+0.063%, hit ~50%.
basis increasing: 17 events, avg short return ~+0.201%, hit ~64.7%.
Do not hard-code basis direction.

IV:
Front IV - next IV >1 vol point + H1 bearish + Negative Gamma + Z<=-2:
24 OOS events; 60m ~+0.158%; 120m ~+0.209%; 120m directional hit ~62.5%.
Use as urgency/volatility context rather than direct direction.

## Rules

1. Freeze state at event time.
2. Never use future Gamma walls.
3. Never use future news.
4. Separate alpha from execution quality.
5. Include spread/slippage/latency.
6. Always show sample size.
7. Prefer OOS over in-sample.
8. Re-test after rule changes.
9. Tiny samples remain hypotheses.
10. Never advertise preliminary statistics as expected returns.

## Next validation

Larger OOS, non-overlapping walk-forward, PBO/DSR/PSR, cost stress, parameter perturbation, regime splits, ablation, bootstrap CI, paper trading and execution-quality measurement.
