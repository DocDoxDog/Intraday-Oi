# TEST PLAN

Status: ARCHITECTURE READY

## Unit

Parser, nulls, IV conversion, contract normalization, expiry mapping, OI/ΔOI, Greeks, GEX, DEX, levels, flow hypotheses.

## Quant

Black-76 analytical checks
source gamma vs derived gamma
IV percent/decimal
DTE boundaries
multiplier
sign variants
multi-expiry aggregation
gamma flip
duplicate contracts
expiry/roll
PIT availability
determinism

## Integration

Source -> raw -> parser -> canonical DB -> quant -> API
Quant -> signal -> Telegram
Database transaction/recovery
Provider failure

## Backtest

Mandatory baselines:
PRICE ONLY
PRICE + VOLUME
PRICE + ATR
PRICE + IV
PRICE + REALIZED VOL
OI ONLY
GEX ONLY
OI + GEX
OI + GEX + IV
FULL MODEL

Metrics:
future return/range
realized-vol error
MAE/RMSE
MFE/MAE
Sharpe/Sortino
max DD
turnover
cost/slippage
economic value added

## PIT leakage

Fail when an observation is used before availability_time, when official corrections leak backward, or when future features enter normalization.

## E2E

Data arrives
-> canonical record
-> quant result
-> dashboard
and independently
-> alert
-> Telegram

## Current test status

Tests exist in both repositories, but this audit did not execute them. Therefore status is not QA PASS.
