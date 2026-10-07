# GOLD MARKET INTELLIGENCE — ENGINEERING SKILL

## Mission
Build a deterministic, evidence-first Gold Market Intelligence system that answers:
1. What is the market state?
2. Where are the structurally important zones?
3. What action must happen at each zone?
4. What confirmation is required?
5. Is the setup still worth trading after structural risk and transaction costs?
6. When is the correct answer WAIT / NO TRADE?

The system is an analysis product, not an execution engine. Order execution authority remains outside Intraday-Oi.

## Core architecture
DATA → PROVENANCE / DATA CLOCK → DETERMINISTIC MARKET STATE → MARKET MAP → REGIME → ACTION ZONES → SETUP / CONFIRMATION → RISK / COST GATE → AI ANALYST → TELEGRAM / DASHBOARD

## Five core engines
### 1. Market State Engine
States: TREND, BALANCE, TRANSITION, EVENT. Regime is a gate, not a trade signal.
### 2. Market Map Engine
Context: Futures / CFD / Spot / Basis; Options OI / ΔOI / IV / Skew / Gamma; Price structure; Auction / Profile; Liquidity; Order flow when supplied; Macro state.
R/S and Gamma levels are structural context. They are not automatically executable targets.
### 3. Action Zone Engine
A level is not an entry. At a zone ask what actually happened: REJECTION, ABSORPTION, ACCEPTANCE, BREAKOUT, RETEST, FAILED_BREAKOUT, BREAKDOWN, STRUCTURE_SHIFT.
A setup becomes actionable from an observed event, not merely because price touched a number.
### 4. Confirmation Engine
Confirmation is setup-specific and should combine price location, market structure, timeframe alignment, BOS / structure shift, order flow, liquidity behavior, and auction context.
Missing optional evidence remains UNKNOWN. Never silently convert missing data into PASS.
### 5. Risk Engine
The deterministic risk boundary owns structural invalidation, risk distance, target qualification, RR, volatility sanity, spread / slippage when available, and cost-adjusted viability.
Bad risk means NO TRADE. Do not force a plan because directional bias exists.

## Three core strategies
### PULLBACK
TREND → IMPULSE → RETRACE → ACTION ZONE → FLOW / REACTION → STRUCTURE CONFIRM → CONTINUE
### BREAKOUT + RETEST
BALANCE → BREAKOUT → ACCEPTANCE → RETEST → FLOW / STRUCTURE → CONTINUE
Breakout is not an entry. A break that immediately returns into prior value is a FAILED_BREAKOUT candidate.
### REVERSAL
EXTREME → STRUCTURAL ZONE → LIQUIDITY / VOLUME → REJECTION / ABSORPTION → STRUCTURE SHIFT → CONFIRM
RSI alone is never sufficient.

## Action state machine
WAIT → APPROACHING → IN_ZONE → TRIGGERED → CONFIRMED
INVALIDATED / NO_TRADE can exit from any actionable state.
WAIT = no relevant setup yet.
APPROACHING = moving toward a defined zone.
IN_ZONE = currently inside the zone; wait for an event.
TRIGGERED = setup event observed; confirmation still required.
CONFIRMED = all required deterministic confirmation checks pass.
INVALIDATED = structural condition fails.
NO_TRADE = setup exists but risk/data/cost gate fails.

## Data clock
Important datum fields: source, clock class, observed_at, as_of when supplied, status, freshness when meaningful, limitations / provenance.
Clock classes: REALTIME, INTRADAY_DERIVED, EOD_DELAYED, SLOW_MACRO.
Never present an EOD/QuikStrike OI snapshot as realtime order flow.

## Order flow rules
Never infer direction from volume alone.
Preferred evidence: explicit aggressor side; bid/ask quote test; trade price location; book changes; derived hypotheses.
Examples: high aggressive volume + little price progress → absorption candidate; selling aggression + bid depletion + acceptance below support → breakdown candidate; selling aggression + support holds + selling intensity fades → selling-absorption reversal candidate.
Any microstructure inference must use language such as 'Observed flow is consistent with …' rather than categorical market-maker claims.

## Auction / profile rules
Current MVP may use bar-based proxies from OHLCV. Label them mode=BAR_PROXY and approximation=CALENDAR_DAY_APPROX.
Do not call a bar proxy a true tick volume profile.
POC / VAH / VAL / HVN / LVN are auction context, not standalone buy/sell signals.

## Macro rules
Macro is slow context: 10Y nominal yield, 10Y real yield, effective Fed funds rate, broad USD, later inflation expectations, COT, ETF flows, central-bank demand.
Use macro to describe tailwinds/headwinds/regime context, not to force an intraday entry.

## Risk and execution boundary
Intraday-Oi never places orders.
The AI must never own contract sizing, broker execution, live order placement, or broker-side SL/TP modification. Those belong to the downstream execution/risk system.

## Research discipline
A new feature is not production because it looks sophisticated.
Required ladder: FEATURE → HYPOTHESIS → EVENT STUDY → OUT-OF-SAMPLE → WALK-FORWARD → COST / SLIPPAGE → REGIME BREAKDOWN → MULTIPLE-TESTING CHECK → SHADOW → PRODUCTION.
Reject features that fail validation.

## Commercial data rights
Before distributing exchange data or derived real-time data to customers, verify provider/exchange licensing, entitlement, redistribution, display, non-display, and derived-data terms. Keep customer-facing data rights separate from internal research use.

## Safe defaults
missing source → UNKNOWN
conflicting evidence → WAIT
missing confirmation → WAIT
unsupported numeric claim → reject / repair
invalid risk ladder → NO_TRADE
stale critical data → WAIT / DEGRADED
market-maker interpretation without direct evidence → hypothesis only

## Engineering style
Prefer small deterministic modules over one giant decision function.
Every new engine should be pure or side-effect-light, structured, explicit about UNKNOWN, regression-tested, non-duplicative, backward-compatible where practical, and customer-language aware.