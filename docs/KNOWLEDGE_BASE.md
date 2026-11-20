# Intraday-OI Knowledge Base

This repository contains executable market knowledge as well as code for the Gold Market Intelligence OS.

## Core philosophy

The system does not ask only BUY or SELL. It asks:
1. What is the market state?
2. What changed?
3. Where is price relative to structure, liquidity and Gamma?
4. What mechanism can explain the move?
5. What creates continuation?
6. What invalidates the thesis?
7. What is the logical target?
8. Is the edge still positive after spread, slippage and latency?
9. Should the answer be NO TRADE?

Core abstraction: FLOW -> PRICE RESPONSE -> MARKET STATE CHANGE.

Indicators are evidence, not the thesis by themselves.

## Knowledge graph

MARKET INTELLIGENCE OS
- KNOWLEDGE: economics, financial economics, microstructure, technical, psychology, market physics
- SKILL: Observe -> Classify -> Diagnose -> Mechanism -> Scenario -> Decision -> Execution -> Review
- SITUATION: normal, trend, range, 3SD, Gamma, flow, liquidity, volatility, macro
- HOW-TO: read market, classify regime, identify liquidity, detect wall break, acceptance/reclaim, OI + price, basis, IV/skew, acceleration, scenario, invalidation, sizing, review

Relationships:
KNOWLEDGE -> SUPPORTS -> SKILL
SKILL -> APPLIES_TO -> SITUATION
SITUATION -> PRODUCES -> EVENT
EVENT -> ACTIVATES -> MECHANISM
MECHANISM -> CHANGES -> PRICE_RESPONSE
SCENARIO -> REQUIRES -> CONDITION
SCENARIO -> INVALIDATED_BY -> CONDITION
TRADE -> BASED_ON -> SCENARIO
TRADE -> PRODUCES -> OUTCOME
OUTCOME -> UPDATES -> KNOWLEDGE
FAILURE -> UPDATES -> RULE

## Gamma

Gamma is a regime/response variable, not a standalone direction signal.

Negative Gamma is an amplifier. Negative Gamma + directional event + acceptance + price response + flow alignment can increase expansion risk.

Gamma Wall state machine:
APPROACHING -> TOUCH -> BREAK -> ACCEPTANCE -> RECLAIM/FAILURE -> EXPANSION

Break + acceptance is a stronger continuation candidate than a simple touch.
Break + weak response + reclaim is a failed-break candidate.
Preferred target: next valid Gamma Wall / liquidity objective.

## OI

OI is positioning geometry, not automatic direction.

Track Put/Call OI, OI change, migration, strike/expiry concentration, barrier geometry and OI + price response.

Migration means positioning moved. It does not automatically mean new longs or new shorts.

Research barrier ratio:
(DeltaPutBelow - DeltaCallAbove) / (abs(DeltaPutBelow) + abs(DeltaCallAbove))

Low ratio + falling price can support a short hypothesis. High ratio + rising price can support a long hypothesis. This remains a hypothesis until replicated OOS.

## IV / skew / DTE

IV is primarily volatility/urgency context.
Track front IV, next IV, IV spread, IV change/acceleration, skew/skew change and DTE.
Do not use IV alone as direction.

## Futures / spot / CFD / basis

BASIS = FUTURES - SPOT.

Track basis, basis change, velocity and acceleration.
For multiple expiries track F1/F2/F3/F4, curve slope/change, contango and backwardation.
Basis is context, not a standalone buy/sell signal.

## 3SD

3SD is a regime detector:
NORMAL -> 3SD TEST -> 3SD BREAK -> ACCEPTANCE / RECLAIM.

Acceptance outside the extreme supports expansion research.
Fast reclaim supports failed expansion / mean reversion research.
When 3SD breaks, normal mean-reversion assumptions may stop working.

## Flow

States:
AGGRESSIVE_BUY, AGGRESSIVE_SELL, ABSORPTION, EXPANSION, EXHAUSTION, FAILED_BREAK.

Interpret flow through price response:
buy pressure up + price up strongly = expansion
buy pressure up + price flat = absorption
sell pressure up + price down strongly = expansion
sell pressure up + price flat = absorption

## Liquidity

Track equal highs/lows, session highs/lows, prior day levels, Gamma Walls, OI Walls, volume/TPO nodes, FVG, order blocks and stop clusters.

A liquidity level is not automatically a target. Determine whether price sweeps, rejects, accepts, reclaims or expands away.

## Market physics

Physics is an abstraction for nonlinear market behavior, not literal physical law.

Mechanisms:
feedback, reflexivity, criticality, cascade, liquidity vacuum, volatility clustering, regime shift, phase transition, nonlinear response and market-time acceleration.

Market-time acceleration proxy:
price velocity + acceleration + event frequency + volume/flow rate + range expansion + liquidity withdrawal.

## Technical hierarchy

MN/W/D/H4/H1/M30/M15/M5/M1.
H4/H1 = context.
M15/M5/M1 = timing.
A low-timeframe signal should not silently override a higher-timeframe regime.

## Scenario engine

Continuation:
Gamma Wall breaks + acceptance + flow follows + structure aligned -> next wall.

Failed break:
wall breaks + weak price response + reclaim -> stop chasing; mean reversion only if separately validated.

Range:
wall holds + flow absorbed + no displacement -> range or NO TRADE.

## Trade plan

A trade intent must contain symbol, direction, entry zone, stop, target, target type, risk %, time horizon, thesis, mechanism, invalidation, scenario ID, confidence and evidence references.

No invalidation = incomplete.
No measurable target = incomplete.
No execution-cost check = incomplete.

## Risk

Hard gate checks risk/trade, daily loss, drawdown, max positions, correlation, exposure, margin, spread, slippage, hours, news, data freshness, execution health, SL/TP, R:R, duplicate positions and account state.

Failure = REJECT. AI cannot override.

## Backtest

MARKET STATE(t) -> EVENT -> SCENARIO -> DECISION -> EXECUTION -> OUTCOME.

Use only information available at t. Freeze options, OI, Gamma, basis, IV, structure and news at event time.

Guard against look-ahead, publication leakage, future Gamma walls, overlapping events, multiple testing, overfitting and optimistic fills.

## Evidence ladder

IDEA -> MECHANISM -> EVENT STUDY -> BACKTEST -> WALK-FORWARD -> PAPER -> LIVE TRACK RECORD -> VERIFIED.

Small OOS samples are hypotheses, not proof.

## AI Trader

Normal: QUANT -> STATE -> RULES -> SCENARIOS.

Critical events can activate Market, Options, Flow, Macro, Physics and Psychology specialists plus Bull, Bear, Critic, Trader and Risk roles.

No simple majority vote. If evidence remains unresolved: NO TRADE.

## MCP

Read tools may expose market/account/research state.
Write tools may create intents/orders/modify/close/cancel, but every write operation must pass the deterministic risk gate.
Never expose broker credentials to LLMs.

## Canonical state

Dashboard, Telegram, AI Trader, backtest replay and MT5 orchestrator consume the same timestamped market state:
timestamp, price, futures, spot, basis, structure, volatility, 3SD, Gamma, options, OI, flow, liquidity, macro, news, physics, psychology, regime, events, scenarios, thesis, intent, risk, execution, data quality.

## Memory

L1 raw: ticks, bars, options, OI, flow, snapshots, events.
L2 episodic: trades, plans, scenarios, outcomes, MFE/MAE.
L3 patterns: regimes, event patterns, conditional outcomes, failures.
L4 knowledge: skills, mechanisms, rules, relationships, hypotheses, validated findings.

Every knowledge item needs version, timestamp, source, evidence level, validation status and limitations.

## Golden rule

The system must be able to say NO TRADE.
A trading AI that always produces a position is not intelligent.
