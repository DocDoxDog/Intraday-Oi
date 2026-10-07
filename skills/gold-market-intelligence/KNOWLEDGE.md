# GOLD MARKET INTELLIGENCE — KNOWLEDGE BASE

## Product thesis
Intraday-Oi is evolving from an OI/GEX dashboard into a Gold Market Intelligence / Market Decision Engine.
The differentiator is the chain: evidence → market state → map → action zone → confirmation → risk → explanation.
The customer should quickly understand: จุดไหนต้องรอ และต้องรอให้ตลาดทำอะไร

## Data semantics
REALTIME: trades, bid/ask, spread, depth, MBO/MBP, order flow when a source actually supplies them.
INTRADAY_DERIVED: delta, cumulative delta, OFI, absorption candidates, liquidity metrics, price-impact estimates.
EOD_DELAYED: options OI, ΔOI, settlement, published positioning.
SLOW_MACRO: FRED yields, Fed policy rate, broad USD, COT, ETF / central-bank demand.
Derived metrics inherit the quality and clock of their inputs.

## Options / Gamma
Useful context: Call Wall, Put Wall, Gamma Mean / Flip, positive / negative gamma zones, IV term structure, skew, OI by strike / expiry.
GEX is not a dealer-position oracle.
Use language such as 'Observed GEX structure is consistent with …' or 'Evidence is insufficient to identify dealer inventory.'

## Order flow
Preferred evidence: explicit aggressor side, bid/ask quote test, trade price location, book changes, then derived hypotheses.
Minimum semantics: aggression, delta, cumulative delta, depth, imbalance, absorption candidate, sweep when the source identifies it.
Never infer direction from candle volume alone.

## Auction / profile
Context: POC, VAH, VAL, HVN, LVN, Initial Balance, Overnight High/Low, Session High/Low.
MVP caveat: OHLCV bar profiles are approximations that allocate bar volume to representative price bins; they are not tick-by-tick executed-volume profiles.

## Market regimes
TREND: aligned higher-timeframe structure; prefer Pullback and Breakout + Retest.
BALANCE: overlapping auction / mixed structure; mean reversion is permitted.
TRANSITION: structure conflict, sweeps, failed breaks, changing value; reversal / failed breakout setups are permitted.
EVENT: high-impact fresh catalyst or data uncertainty; WAIT until reaction is observable.

## Four-route customer map
The customer-facing product should answer “ต้องทำอะไรถึงเข้า?” with four routes:
- BUY breakout/reclaim at resistance
- BUY reaction at support
- SELL rejection at resistance
- SELL breakdown/retest below support

For each route, render Entry reference + SL + TP1/TP2/TP3/TP4/TP5. The route is valid only when its setup event, confirmation, and risk gate are satisfied. A directional market bias changes the preferred route, but the dashboard/Telegram still exposes all four alternatives so a lower support reaction or opposite reversal is not silently discarded.

## Setup semantics
PULLBACK: established trend + impulse + retracement + structural zone + reaction + lower-timeframe continuation.
BREAKOUT + RETEST: break → acceptance → retest → hold/rejection → continuation. Breakout candle is not confirmation.
REVERSAL: extreme → structural zone → liquidity interaction → rejection/absorption → structure shift → confirmation.
These semantics solve the 'large lower volume but no BUY' issue without manufacturing a long setup.

## Risk
A setup is tradable only after structural invalidation, target qualification, volatility sanity, and transaction-cost checks where available.
Core values: entry reference, invalidation, target ladder, risk distance, gross RR, volatility, spread/slippage, cost-adjusted viability.
A wide stop is not fixed by changing arithmetic. Unacceptable risk means NO_TRADE.
Do not hard-code contract size or tick value into generic engines; obtain instrument specs from verified source.

## Macro for Gold
Useful slow variables: nominal 10Y yield, real 10Y yield, policy rate, broad USD, later inflation, COT, ETF flows, central-bank demand.
First-pass context heuristic: real yield ↓ + broad USD ↓ → GOLD_SUPPORTIVE; real yield ↑ + broad USD ↑ → GOLD_HEADWIND; otherwise MIXED / UNKNOWN.
This is context, not an intraday entry signal.

## Trend following
Model trend following as regime + directional structure + momentum + volatility + breakout/pullback, not as one EMA crossover.

## Mean reversion
Regime-gated: TREND → do not fade blindly; BALANCE → mean reversion allowed; TRANSITION → reversal / failed breakout allowed; EVENT → WAIT.

## Confirmation
Long breakout/reclaim needs break + acceptance + retest + hold + lower-timeframe bullish structure.
Short failed-retest needs failure + retest + rejection + bearish lower-timeframe structure.
Long reversal needs support interaction + rejection/absorption + structure shift + bullish confirmation.
Missing order-flow data remains UNKNOWN.

## Current repository reality
Already present: deterministic OI/ΔOI separation, QuikStrike multi-expiry Gamma Matrix, technical context, evidence-first LLM verifier, risk-aware structural invalidation, support-reaction LONG, mobile Gamma Table / Action Zone dashboard, Supabase persistence, Telegram/LINE delivery.
Next generation makes new engines explicit and composable rather than continuing to grow market_state.py.

## Research Lab
Every new feature needs: hypothesis, source/clock, precise definition, event, horizon, benchmark, costs, OOS design, walk-forward, regime slices, failure modes, and shadow/production status.
Do not promote a feature because of one attractive historical example.

## Evidence language
Use: FACT, OBSERVED, DERIVED, CONSISTENT_WITH, CANDIDATE, HYPOTHESIS, UNKNOWN, DEGRADED, WAIT, NO_TRADE.
Avoid categorical causal claims unless the source identifies causality.

## Licensing / customer delivery
CME data rights are a product constraint. Keep internal research fields, customer display fields, derived analytics, source screenshots, and realtime/delayed data distinct.
Before paid distribution of exchange data or derived data, perform an explicit rights review and preserve provenance on every customer-facing surface.

## Research references
CME Gold Futures: https://www.cmegroup.com/markets/metals/precious/gold.html
CME market data / MBO-MBP: https://www.cmegroup.com/market-data.html
CFTC COT: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
FRED DGS10: https://fred.stlouisfed.org/series/DGS10
FRED DFII10: https://fred.stlouisfed.org/series/DFII10
FRED DFF: https://fred.stlouisfed.org/series/DFF
FRED DTWEXBGS: https://fred.stlouisfed.org/series/DTWEXBGS
Cont/Kukanov/Stoikov OFI: https://arxiv.org/abs/1011.6402
Andersen/Bondarenko VPIN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2435904
Almgren/Chriss execution framework: https://www.smallake.kr/wp-content/uploads/2016/03/optliquidation.pdf
Probability of Backtest Overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

These references are design evidence, not proof that any specific feature is profitable.