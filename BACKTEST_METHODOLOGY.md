# Backtest / Quant Validation Methodology

## Principle
The first research target is incremental information, not trading profitability.

## Nested baselines
B0: price only
B1: price + volume
B2: price + ATR
B3: price + IV
B4: price + realized volatility
B5: OI
B6: GEX
B7: OI + GEX
B8: OI + GEX + IV
B9: full validated feature set

## Horizons
5m, 15m, 30m, 1h, 4h, 1D where data resolution supports them.

## Splits
- chronological train/validation/test
- out-of-sample holdout
- purged walk-forward
- embargo around overlapping labels when needed

## Leakage controls
- use publication_time, not merely observation date
- never use official OI before it was published
- do not use future expiry information beyond what was known
- no future IV/Greek values
- align option observations and underlying timestamps
- no survivorship filtering that removes failed/expired contracts from historical universe

## Metrics
Forecast: MAE, RMSE, R², correlation, calibration.
Market outcome: future return, future range, future realized variance/volatility.
Trading simulation only after feature validation: hit rate, expectancy, Sharpe, Sortino, max drawdown, turnover, costs and slippage.

## Robustness
Run by bull/bear/sideways, high/low volatility, expiry/non-expiry, 0DTE/1DTE/weekly/monthly and macro-event sessions.

## Decision rule
If OI/GEX does not improve out-of-sample performance against the relevant baseline with economically meaningful and robust effect sizes, report no incremental edge.
