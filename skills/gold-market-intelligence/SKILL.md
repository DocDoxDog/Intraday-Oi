# GOLD MARKET INTELLIGENCE — ENGINEERING SKILL

## Mission

Build a deterministic, evidence-first Gold Market Intelligence and Flow Engineering system that explains how information, volatility, options risk, liquidity, time and price interact.

The system answers:
1. What is observed?
2. What is derived?
3. What is assumed?
4. What market state are we in?
5. Which structural nodes matter?
6. What event must happen?
7. What path follows?
8. Did the mechanism actually work?

Intraday-Oi is an analysis/intelligence product, not a broker execution engine.

## Core architecture

```text
RAW DATA
  ↓
PROVENANCE + DATA CLOCK
  ↓
SYNCHRONIZED MARKET BUS
  ↓
VOL ENGINE + OPTIONS RISK ENGINE + MICROSTRUCTURE ENGINE
  ↓
MARKET REGIME ENGINE
  ↓
STRUCTURAL MAP ENGINE
  ↓
EVENT / PATH ENGINE
  ↓
SCENARIO / OUTCOME ENGINE
  ↓
CUSTOMER NARRATIVE
  ↓
DASHBOARD / TELEGRAM / RESEARCH LAB
```

## Evidence semantics

FACT
DERIVED
MODEL_ASSUMPTION
CONSISTENT_WITH
HYPOTHESIS
UNKNOWN
DEGRADED
WAIT
NO_TRADE

Missing evidence remains UNKNOWN.

## Options risk engine

### DEX
Support:
- observed portfolio DEX
- modeled dealer DEX

Store:
- underlying-unit delta
- USD delta
- inventory/sign assumption
- source/clock
- model version

### GEX
Use an explicit versioned convention:

```text
GEX = position_sign × Gamma × multiplier × S² × 0.01
```

For GC options use correct Black-76/futures-option conventions.

Mandatory metadata:
- units
- sign convention
- source
- expiry scope
- model version
- assumption set

### Vanna
Vanna = dDelta/dIV.

Use it as the volatility-driven component of delta/hedge change.

### Charm
Charm represents time-driven delta drift and is important near expiration.

### Hedge-pressure decomposition

Compute:

```text
dDelta_price
dDelta_vol
dDelta_time
dDelta_total
dHedge ≈ -dDelta
```

This is a mechanical risk-sensitivity model, not proof of actual dealer flow.

## Gamma semantics

Always separate:
- aggregate gamma regime
- local gamma structure
- Call Wall
- Put Wall
- gamma flip
- gamma mean
- expected-volatility envelope

Positive GEX does not prove that dealers are already hedged.
Negative GEX does not prove a down move.

## Structural nodes

Never fabricate a fixed price ladder.

Node selection combines:
- real observed strike/level
- local prominence
- global concentration
- distance
- expiry coverage
- volatility-scaled relevance
- semantic role

Use tiers:
- anchor/wall
- local barrier
- continuation node
- tail node

The old global 20%-of-max filter may be used as one feature, not the final selector.

## Volatility engine

Required:
- ATM IV
- IV changes
- skew
- term structure
- event premium
- realized volatility
- IV-RV
- clock-normalized percentile/z-score
- regime

Regimes:
VOL_COMPRESSION
VOL_STABLE
VOL_EXPANSION
VOL_DISLOCATION
VOL_EVENT_PREMIUM
VOL_CRUSH

Expected-range bands are probability envelopes, not S/R levels.

## Market-maker engine

Model:
inventory + Greeks + liquidity + balance sheet + DTE + cross-hedging + hedge frequency.

Preferred language:
"consistent with..."

Avoid:
"dealer definitely bought/sold/hedged."

## Fund engine

Represent:
- CTA/trend
- volatility-target
- discretionary macro
- relative-value/volatility
- commercial/hedger
- reportable positioning

COT is slow context.

Do not infer a named fund's live flow without data.

## Macro engine

Gold variables:
real yields, nominal yields, policy expectations, USD, inflation, energy, geopolitics, central-bank demand, ETF/physical demand and cross-asset risk.

Macro changes regime/context, not an automatic entry.

## Microstructure engine

Only activate when source provides:
trades, bid/ask, depth, MBO/MBP, aggressor side and/or cancellations.

Then compute:
OFI, depth, spread, impact, aggression and replenishment.

Never infer true order flow/CVD/absorption/sweeps from bar volume.

## Technical engine

Priority:
H4/H1 structure → M15/M5 tactical state → M1 context.

Use:
trend, swing structure, BOS, acceptance/rejection, retest, ATR/realized volatility and value migration.

Touch ≠ entry.
Wick ≠ break.
Breakout candle ≠ confirmation.

## Econophysics / statistics

Build around:
fat tails, volatility clustering, nonstationarity, seasonality and nonlinear impact.

Prefer:
rolling quantiles, z-scores, clock-matched distributions and regime-conditioned distributions.

Do not use Hurst/scaling as a primary directional signal without independent validation.

## Time / seasonality engine

Persist:
- UTC/NY/London/Tokyo time
- session
- minutes from session open/close
- weekday
- week/month
- DTE
- minutes-to-expiry
- event window
- roll state

Build matched baselines for:
- realized volatility
- volume
- spread/depth when available

## Structural path engine

Every current state must yield:

```text
CURRENT
  ↓
nearest structural node
  ↓
conditional next node
  ↓
continuation node
  ↓
alternate / invalidation
```

Every node has:
- level
- type
- evidence
- role
- distance
- expiry scope
- state
- why-next explanation

## Event engine

Supported:
TOUCH
REJECTION
ACCEPTANCE
BREAK
FAILED_BREAK
RETEST
RECLAIM
CONTINUATION
GAMMA_SIGN_CHANGE
GAMMA_FLIP_CROSS
IV_EXPANSION
IV_COMPRESSION
DEX_SHIFT
VANNA_SHIFT
CHARM_SHIFT
REGIME_CHANGE

Break requires more than a wick.

## Outcome engine

Persist for each event:
- T+1m
- T+5m
- T+15m
- T+30m
- T+60m
- MFE
- MAE
- next-node hit
- time-to-next-node
- realized volatility

## Research protocol

```text
FEATURE
→ HYPOTHESIS
→ EVENT
→ BENCHMARK
→ CONTROLS
→ OOS
→ WALK-FORWARD
→ COSTS
→ REGIME SLICES
→ ABLATION
→ MULTIPLE-TESTING
→ SHADOW
→ PRODUCTION
```

No production promotion from one attractive example.

## Priority roadmap

### P0
Persist OHLCV + synchronized timeline + option snapshots + session metadata.

### P1
DEX + GEX audit/sign contract + local gamma prominence + Vanna + Charm.

### P2
Structural nodes + event state machine + path engine.

### P3
Realized volatility + IV-RV + time/expiry seasonality + dynamic expected range + HAR-RV benchmark.

### P4
Synchronized real-yield/USD/rates/energy/news-surprise/COT context and participant hypotheses.

### P5
True microstructure after source entitlement.

### P6
Outcome store + walk-forward + shadow validation.

## Customer presentation

Do not dump Greeks.

Show:
- Market State
- Current Location
- Options Risk State
- Volatility State
- Structural Path
- What confirms
- What invalidates
- Why the next node matters
- Evidence quality

Trade-plan/execution semantics stay separate from the analysis map according to product delivery rules.

## Safe defaults

missing source → UNKNOWN
conflicting evidence → WAIT
missing confirmation → WAIT
stale critical data → DEGRADED / WAIT
unsupported numeric claim → reject/repair
invalid risk → NO_TRADE
dealer causal claim without evidence → MODEL_ASSUMPTION / CONSISTENT_WITH
fund-flow claim without participant data → HYPOTHESIS / UNKNOWN
