# Flow Engineering Research & System Review v2
## Gold Market Intelligence / Intraday-Oi

**Research date:** 2026-10-08  
**Working branch:** `feat/decision-engine-flow-architecture-v1`

This document is the research-derived knowledge layer for the next generation of Intraday-Oi. It translates volatility engineering, DEX/GEX/second-order Greeks, market-maker mechanics, fund behavior, macroeconomics, microstructure, psychology, technical analysis, econophysics, quant methods, time/seasonality and time-series analysis into testable system components.

---

## 1. Executive synthesis

The main lesson is that Intraday-Oi should stop treating IV, GEX, OI, technical indicators, news and price levels as independent "signals".

The correct engineering object is a **time-indexed market state transition**:

```text
Information / Macro / Event
        ↓
Volatility surface + options positioning
        ↓
Participant risk sensitivities
        ↓
Liquidity / order-book response
        ↓
Price discovery / auction
        ↓
Technical structure
        ↓
Next market state
```

For options, GEX is only one derivative of the portfolio risk state. A serious volatility-flow engine should expose:

- DEX
- GEX
- Vega
- Vanna
- Charm
- Volga/Vomma where data quality justifies it
- IV level/change
- skew
- term structure
- realized volatility
- IV-RV spread
- event premium
- time-to-expiry
- expiry concentration

The important object is the **change in portfolio delta**:

```text
dDelta ≈ Gamma*dS + Vanna*dIV + dDelta/dt*dt + higher-order terms
dHedge ≈ -dDelta      (under a delta-hedging assumption)
```

That is more informative than the shorthand "positive GEX means sideways".

Public OI does not identify dealer inventory. Dealer DEX/GEX are therefore conditional models that require an explicit inventory/sign convention. A 2026 methodology/reproducibility study makes this sign assumption a central issue.

The system should evolve from:

```text
snapshot → indicators → narrative
```

to:

```text
raw time series
→ synchronized observations
→ risk/flow state
→ market regime
→ structural nodes
→ event
→ path
→ outcome
→ validated narrative
```

---

## 2. Epistemic contract

Every field must be classified as one of:

### FACT
Directly observed from an entitled source.

### DERIVED
Deterministically calculated from observed data.

### MODEL_ASSUMPTION
Requires an assumption that is not directly observable.

### CONSISTENT_WITH
Evidence is compatible with a mechanism but does not establish causality.

### HYPOTHESIS
A testable proposition awaiting validation.

### UNKNOWN
Required evidence is unavailable.

### DEGRADED / WAIT / NO_TRADE
Operational states.

Examples:
- OI = FACT
- Black-76 Gamma = DERIVED
- dealer-modeled GEX = DERIVED + MODEL_ASSUMPTION
- "dealer is buying now" = UNKNOWN without actual inventory/flow evidence
- "price response is consistent with short-gamma amplification" = CONSISTENT_WITH

Never silently promote UNKNOWN into FACT.

---

## 3. Volatility engineering

### 3.1 IV is a surface, not one number

ATM IV is only the center of the risk surface.

Minimum volatility state:

```text
ATM IV
IV change by horizon
skew
term structure
surface curvature
realized volatility
IV - realized volatility
event premium
expiry concentration
regime
confidence
```

CME CVOL/QuikStrike and Cboe volatility tools emphasize volatility surfaces/term structures rather than a single isolated IV.

### 3.2 Dynamic volatility regimes

Suggested regimes:

- VOL_COMPRESSION
- VOL_STABLE
- VOL_EXPANSION
- VOL_DISLOCATION
- VOL_EVENT_PREMIUM
- VOL_CRUSH

Baselines must be clock-aware. Intraday volatility is seasonal, so the same 5-minute move should be compared with the distribution for the same clock/session bucket rather than with an all-day average.

### 3.3 Implied vs realized volatility

Persist realized volatility at multiple horizons:

```text
1m / 5m / 15m / 30m / 1h / session / day
```

Use:

```RV_h = sum(r_i^2)
VRP_proxy = IV - RV
```

Treat the second quantity as a descriptive proxy, not an automatic trading edge.

### 3.4 Expected range

A standard approximation is:

```text
EM_h = S × IV × sqrt(h/T)
```

Use instrument-specific day-count conventions.

1σ/2σ/3σ are **probability envelopes**, not support/resistance. They must not be merged semantically with gamma walls.

---

## 4. DEX / GEX / Vanna / Charm

### 4.1 DEX

Separate:

1. observed/known portfolio DEX;
2. modeled dealer DEX.

Underlying-unit DEX:

```text
DEX_units = position × Delta × multiplier
```

Dollar delta:

```text
DEX_USD = position × Delta × multiplier × S
```

Store units explicitly and attach the inventory assumption to dealer-modeled DEX.

### 4.2 GEX

A common dollar-per-1%-move convention is:

```text
GEX_1pct = position_sign × Gamma × multiplier × S² × 0.01
```

For GC/futures options use the correct Black-76/futures-option conventions.

The existing engine uses `dealer_call_positive_put_negative`. This convention should become first-class, versioned and test-covered.

Important mathematical distinction:

**Long call gamma and long put gamma are both positive.** A negative put contribution inside a dealer GEX aggregate comes from the assumed dealer inventory sign, not from gamma itself.

### 4.3 Aggregate gamma vs local gamma

Keep two separate states:

```text
AGGREGATE_GAMMA_REGIME
LOCAL_GAMMA_STRUCTURE
```

A global positive GEX can coexist with a local negative concentration.

Therefore a global "20% of maximum |GEX|" selector is insufficient. A locally important barrier can be smaller than the largest global concentration.

### 4.4 Gamma flip

Gamma flip, gamma mean, Call Wall, Put Wall, maximum concentration and expected range are different semantic objects and need different provenance.

### 4.5 Vanna

```text
Vanna = ∂Delta/∂IV = ∂Vega/∂S
dDelta_vanna ≈ Vanna × dIV
```

Vanna matters when IV changes strongly during a price move. A gamma-only engine misses this volatility-driven delta change.

### 4.6 Charm

Charm is time-driven delta drift:

```text
Charm ≈ -∂Delta/∂t
```

The sign convention must be explicit.

Charm becomes increasingly important as DTE becomes small.

### 4.7 Volga/Vomma

```text
Volga/Vomma = ∂Vega/∂IV
```

Keep below DEX/GEX/Vanna/Charm in priority until reliable input data and validation exist.

---

## 5. Market-maker mechanics

Market makers are not a single directional actor. Relevant mechanisms include:

- inventory
- delta/gamma/vega risk
- balance sheet
- liquidity
- quote risk
- hedge frequency
- cross-hedging
- adverse selection

Under a **long-gamma dealer assumption**:
- spot up → delta rises → hedge tends to sell;
- spot down → delta falls → hedge tends to buy.

This can be stabilizing.

Under short gamma, hedge direction can reinforce the initial move.

These are conditional mechanism statements, not unconditional forecasts.

Correct wording:

> Observed options structure is consistent with a hedge-sensitive regime under the stated inventory assumptions.

Avoid:

> Market Maker already hedged, so price must stay sideways.

Transmission also depends on distance to the concentration, realized volatility, depth, hedge frequency, DTE and IV response.

---

## 6. Fund-trader mechanics

"FUND" must be decomposed into participant classes.

### CTA / time-series momentum

Use proxies such as:
- multi-horizon trend
- breakout persistence
- volatility scaling
- cross-asset confirmation

Academic evidence supports time-series momentum as a useful framework for understanding CTA-style returns.

### Volatility-target / risk-control portfolios

Research documents exposure reduction when volatility rises for volatility-managed portfolios.

But without actual flow/position data, never write "funds are selling".

Use:

> Market state is compatible with risk-targeting de-risking.

### Discretionary macro

Track:
- policy expectations
- real/nominal yields
- USD
- inflation/growth surprises
- geopolitics
- cross-asset correlations

### Relative-value / volatility

Potential exposures:
- skew
- term structure
- calendar spreads
- volatility spreads
- dispersion

Do not infer a particular strategy from one symbol's OI.

### COT

COT is a slow positioning/context layer, not intraday aggressor flow.

---

## 7. Financial engineering

Treat the option value as:

```text
V = V(S, sigma, t, r, ...)
```

A local expansion is:

```text
dV ≈ Delta*dS + 0.5*Gamma*(dS)^2 + Vega*dSigma + Theta*dt + cross terms
```

The system should support scenario stress rather than one-direction labels.

Example scenarios:

```text
A: dS=+20, dIV=-2 vol points
B: dS=-20, dIV=+4 vol points
C: dS≈0, dIV=-5 vol points, dt=1 day
```

For each scenario estimate:
- DEX change
- GEX hedge component
- Vanna hedge component
- Charm/time component
- expected-range shift
- structural-node changes
- regime-transition risk

This is a transparent financial-engineering laboratory, not a black-box signal.

---

## 8. Macro-economic layer

Gold macro should be a time-aligned causal-context graph rather than a single bullish/bearish score.

Core chain:

```text
Policy expectations
→ nominal yields
→ real yields
→ USD
→ opportunity cost / liquidity
→ gold
```

Other channels:
- inflation expectations
- energy
- geopolitics
- central-bank demand
- ETF/physical demand
- global risk sentiment

Macro relationships are regime dependent. Simultaneous moves also make causal attribution difficult.

Recommended state:

```text
Real yield
USD
Policy pricing
Inflation
Energy
Risk premium
Cross-asset confirmation
→ GOLD_SUPPORTIVE / GOLD_HEADWIND / MIXED / UNKNOWN
```

Every macro input needs its own timestamp and freshness.

---

## 9. Microeconomics / market microstructure

Price formation depends on:
- spread
- depth
- aggressive trades
- resting liquidity
- cancellations
- queue state
- inventory
- adverse selection
- price impact

Cont-Kukanov-Stoikov research motivates treating order-flow imbalance and market depth as first-class variables when true MBO/MBP/trade data is available.

A useful research relationship is:

```text
DeltaPrice ≈ beta × OFI
beta tends to increase as depth falls
```

Do not activate this engine with candle volume alone.

No true aggressor side → no honest CVD.
No true book/trade evidence → no honest absorption/sweep claim.

---

## 10. Psychology / behavioral finance

Psychology should be represented as **observable hypotheses**, not mind reading.

Relevant mechanisms include:
- limited attention
- overconfidence
- diagnostic expectations / overreaction
- event salience
- information processing delays

Potential testable states:

### Breakout chase
Large price expansion + attention/news spike + late acceleration.

### Anchoring
Repeated interaction around a salient structural level.

### Post-event overreaction
Large price/IV shock followed by measured reversal or volatility compression.

Correct language:

> Price/volatility behavior is consistent with post-event risk reduction.

Avoid:

> Traders are scared.

---

## 11. Technical analysis as state estimation

Technical analysis should become a structural state machine:

```text
Trend
→ impulse
→ retracement
→ structural zone
→ reaction
→ acceptance/rejection
→ retest
→ continuation/failure
```

Priority:

```H4/H1 structure → M15/M5 tactical → M1 context
```

Indicators are secondary evidence.

Rules:
- touch ≠ entry
- wick ≠ confirmed break
- breakout candle ≠ confirmation

---

## 12. Econophysics

Empirical finance documents stylized facts including:

- fat tails
- volatility clustering
- nonstationary volatility
- persistence in volatility
- intraday seasonality
- aggregation/scaling effects
- nonlinear price impact

Engineering consequence:

Use:
- rolling quantiles
- rolling z-scores
- clock-matched distributions
- regime-conditioned distributions
- tail estimates

Avoid universal static thresholds unless empirically calibrated.

Hurst/scaling estimates should remain research diagnostics because nonstationarity and volatility clustering can create misleading apparent long memory.

---

## 13. Quant / time-series

### Realized volatility

Persist multi-horizon returns and realized-volatility measures.

### HAR-RV

Use Heterogeneous Autoregressive realized volatility as a transparent benchmark before adding complex forecasting.

### GARCH / stochastic volatility

Use as competing volatility forecasts and compare them OOS.

### Tail modeling

Use empirical quantiles, Expected Shortfall and EVT candidates for tails. A Gaussian 3σ rule should not be assumed accurate in heavy-tailed markets.

### Change-point detection

Research candidates:
- CUSUM
- Bayesian change-point
- HMM/state-space
- rolling distribution shifts

Production state should remain interpretable.

---

## 14. Time / seasonal engineering

Time is a state variable.

Persist:

```text
UTC time
New York / London / Tokyo time
session
minutes from session open
minutes to session close
weekday
week/month
DTE
minutes-to-expiry
macro-event window
contract-roll state
```

Build:

```E[RV | clock bucket, session, weekday, regime]```

and matched volume baselines.

Gold has meaningful intraday session structure, so a 5-minute volatility observation should be normalized against its clock/session history.

For short-dated weekly/daily options, DTE and minutes-to-expiry should be treated as state variables, not metadata.

---

## 15. Flow Engineering architecture

The core should have five layers:

### A. Information Flow
macro surprises, news, policy expectations, event risk

### B. Volatility Flow
IV, skew, term structure, IV change, IV-RV, event premium

### C. Risk-Transfer Flow
DEX, GEX, Vanna, Charm, Vega, Volga

### D. Liquidity Flow
spread, depth, OFI, aggression, cancellations, price impact

### E. Price/Auction Flow
trend, range, value migration, break, retest, rejection, acceptance

The core question becomes:

> What pressure is being created, by which mechanism, at what time, and what price response would confirm or reject it?

---

## 16. Structural path engine

A price level is not enough. Maintain a path graph.

Example:

```text
Current 4122
  ↑ 4134 local resistance / gamma node
  ↓ 4114 local downside barrier
  ↓ 4099 secondary node
  ↓ 4074 Put Wall
  ↓ 4049 deeper node
```

Every node should carry:
- level
- semantic type
- source
- expiry scope
- DEX
- GEX
- IV
- OI
- local prominence
- distance
- role
- state
- why-next explanation

Do not collapse Wall, gamma flip, mean and 3SD into one generic support/resistance type.

---

## 17. Event engine

Possible events:

```text
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
```

A break must not be defined merely as low < level or high > level.

Use a calibrated sequence:

```text
penetration
→ close beyond
→ persistence / acceptance
→ retest when applicable
```

Tolerance should be conditioned on tick size and volatility.

---

## 18. Science-experimental protocol

Every feature becomes an experiment.

Required fields:
- hypothesis
- mechanism
- source/clock
- precise event definition
- population
- horizon
- benchmark
- controls
- expected direction
- cost/slippage model
- OOS method
- walk-forward method
- regime slices
- failure conditions
- status

### Hypothesis H1
Modeled positive gamma is associated with lower subsequent realized range after price interacts with a locally significant gamma node.

Controls:
- clock/session
- DTE
- IV regime
- macro-event proximity

Benchmark:
matched non-gamma structural levels.

Horizons:
5m / 15m / 30m / 60m.

### Hypothesis H2
Local gamma prominence predicts the next structural node better than the current global 20%-of-max filter.

Metrics:
- next-node recall
- false-barrier rate
- time-to-next-node
- distance error
- path completion rate

### Hypothesis H3
Vanna adds explanatory power beyond GEX during high IV-change events.

Compare:
- A: price + GEX
- B: price + GEX + Vanna
- C: price + GEX + Vanna + Charm

Use out-of-sample incremental explanatory power and calibration, not only in-sample fit.

---

## 19. Current repository review

| Layer | Current rating | Main issue |
|---|---:|---|
| Options raw/derived context | 8/10 | Strong foundation, incomplete risk surface |
| Decision architecture | 8/10 | Strong deterministic boundary, needs richer state |
| Customer narrative | 7.5/10 | Better structure, still limited by missing timeline |
| OHLC persistence | 3/10 | Raw bars fetched then discarded |
| DEX | 2/10 | No first-class exposure engine |
| Vanna/Charm | 1/10 | Missing |
| Gamma node selection | 4/10 | Global threshold can drop local barriers |
| Event store | 3/10 | No durable touch/break/retest sequence |
| Outcome store | 2/10 | No systematic forward validation |
| OI vs order-flow semantics | 8/10 | Correctly avoids false aggressor claims |
| True microstructure | 2/10 | No MBO/MBP/aggressor feed |
| Macro time-series | 5/10 | Context exists but not synchronized deeply |
| Seasonal/time conditioning | 3/10 | Session/clock baselines missing |
| Vol forecasting | 4/10 | Need realized-vol history + benchmarks |
| Research infrastructure | 2/10 | Hypotheses exist, durable outcomes do not |

### Main conclusion

The largest weakness is **not lack of indicators**.

It is the lack of a persistent, synchronized **time axis** that lets the system answer:

```What existed → what changed → what price did → what happened next?
```

---

## 20. Target architecture

```text
PRICE OHLCV ───────────────┐
OPTIONS SNAPSHOTS ────────┤
MACRO / NEWS ─────────────┤
MICROSTRUCTURE (when real)┤
TIME / SESSION ───────────┘
             ↓
      SYNCHRONIZED DATA BUS
             ↓
   ┌─────────┼─────────┐
   ↓         ↓         ↓
 VOL       OPTIONS    MICRO
 ENGINE     RISK      ENGINE
             ↓
        MARKET REGIME
             ↓
      STRUCTURAL MAP
             ↓
       EVENT + PATH
             ↓
       SCENARIO / OUTCOME
             ↓
          NARRATIVE
```

---

## 21. Required data objects

### `market_bars`
- source
- instrument
- timeframe
- bar_time
- open/high/low/close
- volume
- session
- timezone
- quality

Unique key:

```
(source, instrument, timeframe, bar_time)
```

### `option_risk_snapshots`
- snapshot/time
- expiry
- strike
- option type
- OI
- volume
- IV
- Delta/Gamma/Vega/Theta
- Vanna/Charm/Volga
- option price

### `risk_surface_snapshots`
- net DEX
- net GEX
- net Vega
- net Vanna
- net Charm
- gamma flip
- gamma mean
- Call Wall
- Put Wall
- sign convention
- assumption set

### `structural_nodes`
- level futures/CFD
- node type
- role
- expiry scope
- DEX/GEX/IV/OI context
- local prominence
- tier

### `market_events`
- event time
- event type
- level
- previous state
- new state
- evidence
- price/vol/options state

### `event_outcomes`
- event id
- horizon
- forward price/return
- MFE
- MAE
- hit-next-node
- time-to-next-node
- realized volatility

---

## 22. System-wide priority roadmap

### P0 — Data integrity
1. Persist OHLCV.
2. Synchronize timestamps.
3. Preserve option-chain snapshots.
4. Add session/clock metadata.
5. Build replayable market timeline.

### P1 — Options risk engineering
1. DEX.
2. GEX audit contract and sign-convention metadata.
3. Local gamma prominence.
4. Vanna.
5. Charm.
6. Expiry-aware risk state.

### P2 — Structural path
1. Tiered real nodes.
2. Path ordering.
3. Event state machine.
4. Break/acceptance/retest detector.

### P3 — Volatility/time
1. Realized vol.
2. IV-RV.
3. Clock-normalized volatility state.
4. Dynamic expected range.
5. HAR-RV benchmark.
6. DTE/minutes-to-expiry state.

### P4 — Macro/fund context
1. Real yields.
2. Nominal yields.
3. USD.
4. Inflation/energy.
5. Event surprise.
6. COT.
7. Trend/volatility-target hypotheses.

### P5 — Microstructure
Only after real source entitlement:
1. OFI.
2. Aggressor flow.
3. Depth.
4. Spread.
5. Price impact.
6. Absorption/sweep candidates.

### P6 — Validation
1. Event/outcome store.
2. Walk-forward.
3. Matched benchmarks.
4. Ablation tests.
5. Regime slices.
6. Multiple-testing controls.
7. Shadow deployment.
8. Production promotion.

---

## 23. Customer-facing semantics

Do not dump raw Greeks.

The product should explain a causal market map:

```text
MARKET STATE
CURRENT LOCATION
OPTIONS RISK STATE
VOLATILITY STATE
STRUCTURAL PATH
WHAT CONFIRMS
WHAT INVALIDATES
WHY THE NEXT NODE MATTERS
EVIDENCE QUALITY
```

Example:

> Modeled gamma is positive under the stated dealer-sign convention. Price is currently between 4134 resistance and 4114 local downside barrier. A sustained break/acceptance below 4114 would make 4099 the next structural node; continuation below that would expose the Put Wall near 4074.

This is much more useful than simply displaying GEX = +21M.

---

## 24. Non-negotiable rules

1. GEX is not a dealer-position oracle.
2. DEX/GEX are conditional models unless inventory is known.
3. Positive GEX does not prove hedges are completed.
4. Negative GEX is not automatically bearish.
5. OI is not order flow.
6. Volume is not aggressor side.
7. 3SD is not support/resistance.
8. Gamma mean is not a gamma wall.
9. Gamma flip is not Put Wall.
10. A price touch is not confirmation.
11. A wick is not necessarily a break.
12. One attractive historical example is not evidence of a robust edge.
13. Static thresholds must be empirically calibrated.
14. Missing evidence stays UNKNOWN.
15. Every production claim must be replayable from stored evidence.
16. Never claim absorption, sweep, CVD or true order flow without the required raw data.
17. Market-maker and fund behavior are participant hypotheses unless directly evidenced.
18. Keep source rights/provenance attached to all exchange-derived customer data.

---

## 25. Research references

### Options / volatility
- CME Options Greeks: https://www.cmegroup.com/education/courses/option-greeks.html
- CME Gamma: https://www.cmegroup.com/ko/education/courses/option-greeks/options-gamma-the-greeks.html
- CME QuikStrike Expected Range: https://www.cmegroup.com/tools-information/quikstrike/quikstrike-vol2vol-expected-range-user-guide.html
- CME Metals Options Reports: https://www.cmegroup.com/newsletters/metals-options-update.html
- Cboe Options Institute: https://www.cboe.com/optionsinstitute/research
- Cboe Volatility Term Structure: https://www.cboe.com/tradable-products/vix/term-structure
- OptionsEducation Gamma: https://www.optionseducation.org/advancedconcepts/gamma
- NBER Demand-Based Option Pricing: https://www.nber.org/papers/w11843

### Market structure
- SEC Market Structure Analytics: https://www.sec.gov/featured-topics/market-structure-analytics/research-analysis-market-structure
- Federal Reserve Trading/Capital Markets: https://www.federalreserve.gov/boarddocs/SupManual/trading/trading.pdf
- Federal Reserve dealer inventory constraints: https://www.federalreserve.gov/econres/notes/feds-notes/dealer-inventory-constraints-in-the-corporate-bond-market-during-the-covid-crisis-20210715.html

### Microstructure / quant
- Cont, Kukanov, Stoikov OFI: https://arxiv.org/abs/1011.6402
- Andersen et al. Realized Volatility: https://www.nber.org/papers/w8160
- Corsi HAR-RV: https://academic.oup.com/jfec/article-abstract/7/2/174/856522
- Bouchaud Price Impact: https://arxiv.org/abs/0903.2428
- Microstructure Invariance: https://www.sciencedirect.com/science/article/pii/S1386418116303123

### Econophysics
- Chakraborti et al. review: https://arxiv.org/abs/0909.1974
- Econophysics empirical review: https://www.tandfonline.com/doi/full/10.1080/14697688.2010.539248
- 2026 stylized-facts study: https://www.sciencedirect.com/science/article/pii/S2405918826000218

### Macro / funds
- CFTC COT: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- CME Gold Futures: https://www.cmegroup.com/markets/metals/precious/gold.html
- Moreira & Muir, Volatility Managed Portfolios: https://www.nber.org/papers/w22208
- Baltas & Kosowski, Momentum / CTA framework: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1968996

### Psychology
- Peng & Xiong, Investor Attention: https://www.nber.org/papers/w11400
- Bordalo, Gennaioli & Shleifer, Diagnostic Expectations: https://www.nber.org/papers/w30356
- Limited Attention: https://academic.oup.com/rfs/article/35/2/962/6226477

### 2026 GEX methodology
- Chilingarian, dealer gamma sign methodology: https://papers.ssrn.com/sol3/Delivery.cfm/7131778.pdf
- Gold/SP GEX methodology: https://papers.ssrn.com/sol3/Delivery.cfm/7098358.pdf

The 2026 SSRN papers are methodology references, not settled consensus. They must be independently validated before production use.
