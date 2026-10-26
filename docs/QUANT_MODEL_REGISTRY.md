# Quant Model Registry

The registry is the controlled boundary between mathematical research and production reasoning.

| Model family | Status | Production authority |
|---|---|---|
| Black-Scholes-Merton | reference candidate | NONE |
| Bachelier | reference candidate | NONE |
| CRR/binomial | reference candidate | NONE |
| Monte Carlo | research candidate | NONE |
| IV solver | high-value candidate | NONE |
| Greeks | high-value candidate | NONE |
| Realized volatility | high-value candidate | NONE |
| IV term structure | research candidate | NONE |
| Volatility surface | research candidate | NONE |
| SVI calibration | research candidate | NONE |
| Implied distribution | research candidate | NONE |
| Stochastic volatility | research candidate | NONE |
| Regime-switching SDE | research candidate | NONE |

## Promotion rule
A mathematically correct formula is not sufficient for production promotion.

Promotion requires:
1. mathematical tests
2. numerical tests
3. point-in-time data contract
4. provenance
5. calibration/validation evidence where applicable
6. deterministic regression
7. failure behavior
8. explicit model version

## Relationship to reasoning
The model supplies structured evidence. Reasoning determines how it relates to price structure, options positioning, volatility, flow/intent, events and conflicts. The LLM may explain the relationship but may not change model outputs.