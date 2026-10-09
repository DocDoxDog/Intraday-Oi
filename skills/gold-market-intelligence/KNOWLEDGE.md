# GOLD MARKET INTELLIGENCE — KNOWLEDGE BASE

## Product thesis

Intraday-Oi is a Gold Market Intelligence / Flow Engineering system.

```text
Evidence → Time-aligned State → Risk/Flow Mechanism → Structural Map → Event → Path → Outcome → Narrative
```

It is an analysis/intelligence product, not a broker execution engine.

## Epistemic contract

Use explicit evidence semantics:

- FACT
- DERIVED
- MODEL_ASSUMPTION
- CONSISTENT_WITH
- HYPOTHESIS
- UNKNOWN
- DEGRADED
- WAIT
- NO_TRADE

Public OI does not identify dealer inventory. Dealer DEX/GEX are therefore modeled proxies unless actual inventory is known. Inventory/sign convention must be explicit and versioned.

## Volatility

Volatility is a surface and time-series state, not one number.

Minimum state:
- ATM IV
- IV change by horizon
- realized volatility
- IV-RV
- skew
- term structure
- event premium
- expiry concentration
- clock-normalized percentile/z-score
- regime

Recommended regimes:
VOL_COMPRESSION, VOL_STABLE, VOL_EXPANSION, VOL_DISLOCATION, VOL_EVENT_PREMIUM, VOL_CRUSH.

1σ/2σ/3σ are probability envelopes, not support/resistance.

## Options risk

First-class exposures:
- Delta
- Gamma
- Vega
- Vanna
- Charm
- Volga/Vomma where validated

Core differential:

```text
dDelta ≈ Gamma*dS + Vanna*dIV + dDelta/dt*dt + higher-order terms
dHedge ≈ -dDelta   (under delta-hedging assumption)
```

### DEX
Store observed portfolio DEX and modeled dealer DEX separately. Store underlying-unit and dollar units.

### GEX
Common convention:

```text
GEX = position_sign × Gamma × multiplier × S² × 0.01
```

Call-positive/put-negative is an inventory/sign assumption, not a mathematical property of option gamma.

### Vanna
Vanna = dDelta/dIV. Use it for volatility-driven delta/hedge changes.

### Charm
Charm represents time-driven delta drift and becomes especially important near expiry.

## Gamma semantics

Separate:
- aggregate gamma regime
- local gamma structure
- Call Wall
- Put Wall
- gamma flip
- gamma mean
- expected-volatility envelope

Positive modeled GEX can be consistent with stabilizing hedge behavior under a long-gamma dealer assumption; negative modeled GEX can be consistent with reinforcing hedge behavior. Neither is an unconditional direction signal.

## Market makers

Model:
inventory + Greeks + balance sheet + liquidity + DTE + cross-hedging + hedge frequency.

Avoid categorical claims about actual dealer buying/selling/hedging without direct evidence.

## Fund traders

Separate:
- CTA / time-series momentum
- volatility-target / risk-control
- discretionary macro
- relative-value / volatility
- commercial/hedger
- other reportable positioning

COT is slow positioning context.

## Macro

Gold context:
- policy expectations
- nominal yields
- real yields
- USD
- inflation/inflation expectations
- energy
- geopolitics
- central-bank demand
- ETF/physical demand
- cross-asset risk

Macro changes regime/context; it does not directly produce an intraday entry.

## Microstructure

True order flow requires real trades/quotes/depth/MBO/MBP/aggressor-side data.

Never call candle-volume behavior CVD, absorption or sweep.

## Technical analysis

Prioritize H4/H1 → M15/M5 → M1.

Core sequence:
touch → response → acceptance/rejection → retest → continuation/failure.

## Econophysics

Use evidence on:
- fat tails
- volatility clustering
- nonstationarity
- intraday seasonality
- nonlinear price impact

Engineering implication:
use rolling, conditional and clock-matched distributions rather than universal static thresholds.

Hurst/scaling remains a research diagnostic unless independently validated.

## Time / seasonality

Persist:
- session
- timezone
- minutes from open/close
- weekday
- week/month
- DTE
- minutes-to-expiry
- macro windows
- roll state

Build clock/session-conditioned baselines for volatility and volume.

## Structural path

A current market state should map to a sequence of real structural nodes, never a synthetic fixed-price ladder.

Node fields:
level, semantic type, source, expiry scope, OI/IV/DEX/GEX context, local prominence, distance, role and state.

## Events

Use:
TOUCH, REJECTION, ACCEPTANCE, BREAK, FAILED_BREAK, RETEST, RECLAIM, CONTINUATION, GAMMA_SIGN_CHANGE, GAMMA_FLIP_CROSS, IV_EXPANSION, IV_COMPRESSION, DEX_SHIFT, VANNA_SHIFT, CHARM_SHIFT, REGIME_CHANGE.

A wick is not a break.

## Research discipline

Every feature:
hypothesis → event → horizon → benchmark → controls → cost → OOS → walk-forward → regime slices → ablation → multiple-testing → shadow → production.

One attractive example is not sufficient.

## Required next data objects

- market_bars
- option_risk_snapshots
- risk_surface_snapshots
- structural_nodes
- market_events
- event_outcomes

## Current main gaps

1. Persistent OHLC timeline
2. DEX
3. Vanna
4. Charm
5. Local gamma prominence
6. Structural event store
7. Outcome tracking
8. Realized-volatility/time-seasonality engine
9. Synchronized macro time series
10. True microstructure after source entitlement

## Research references

- CME Options Greeks: https://www.cmegroup.com/education/courses/option-greeks.html
- CME Gamma: https://www.cmegroup.com/ko/education/courses/option-greeks/options-gamma-the-greeks.html
- CME Expected Range: https://www.cmegroup.com/tools-information/quikstrike/quikstrike-vol2vol-expected-range-user-guide.html
- CME Metals Options Reports: https://www.cmegroup.com/newsletters/metals-options-update.html
- Cboe Options Institute: https://www.cboe.com/optionsinstitute/research
- Cboe Volatility Term Structure: https://www.cboe.com/tradable-products/vix/term-structure
- NBER Demand-Based Option Pricing: https://www.nber.org/papers/w11843
- Cont/Kukanov/Stoikov OFI: https://arxiv.org/abs/1011.6402
- Realized Volatility: https://www.nber.org/papers/w8160
- HAR-RV: https://academic.oup.com/jfec/article-abstract/7/2/174/856522
- Bouchaud Price Impact: https://arxiv.org/abs/0903.2428
- Econophysics review: https://arxiv.org/abs/0909.1974
- CFTC COT: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- Volatility managed portfolios: https://www.nber.org/papers/w22208
- CTA momentum: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1968996
- Investor attention: https://www.nber.org/papers/w11400
- 2026 GEX sign methodology: https://papers.ssrn.com/sol3/Delivery.cfm/7131778.pdf
