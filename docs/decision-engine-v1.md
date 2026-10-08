# Decision Engine v1 — Flow Engineering Contract

## Purpose

Intraday-Oi now treats market interpretation as a deterministic state machine:
Evidence → Interpretation → Confirmation → Decision → Narrative

The LLM is an explanation layer. It does not own market state or confirmation.

## Canonical layers

1. Structural bias — H4/H1 aligned direction.
2. Tactical direction — M15/M5 behaviour relative to structure.
3. Options context — OI activity, IV movement, Gamma regime.
4. Location / trigger — current price relative to local action-zone levels.
5. Confirmation — price + structure + M5 BOS + catalyst gate.
6. Decision state — confirmed side or wait/developing state.

## State semantics

- BULLISH / BEARISH = structural view only.
- *_AGAINST_STRUCTURE = short-term movement against the structural view; not a reversal claim.
- NOT_CONFIRMED = no valid price confirmation.
- TRIGGERED_WAIT_CONFIRMATION = price event happened but confirmation is incomplete.
- CONFIRMED = structural direction + price event + M15/M5 alignment + M5 BOS, with no event gate blocking it.
- WAIT_TRANSITION = H4/H1 conflict.
- WAIT_BEARISH / WAIT_BULLISH = structural direction exists, but price confirmation is still missing.

## Options rules

- OI / ΔOI / Churn = positioning activity, not aggressor direction.
- Positive GEX = possible dampening context, not a guaranteed range.
- Negative GEX = possible amplification context, not a bearish signal by itself.
- IV is never called high or low without a baseline/percentile.
- Options evidence cannot override price confirmation.

## Trigger vs confirmation

A price crossing a structural level is only a trigger event. It is not confirmation.

Confirmation requires the supplied price/technical evidence to agree with the structural direction. This prevents:

H4/H1 bearish + M5 bullish → CONFIRMED SELL

and instead yields:

Structural Bias = BEARISH
Tactical Direction = BULLISH_AGAINST_STRUCTURE
Confirmation = NOT_CONFIRMED
Decision = WAIT_BEARISH

## Output contract

Customer output is built from the same canonical decision object:

- MARKET READ
- VOLATILITY
- OI POSITIONING
- FLOW STATEMENT
- CONFIRMATION
- WHY NOW
- TECHNICAL
- MACRO/NEWS

The narrative layer must not re-invent the decision state.

## Compatibility

decision_framework remains as an adapter for legacy consumers and tests. New code should use market_state.decision as the canonical source.

trade_plan_engine may expose route-level confirmation, but a counter-trend route cannot promote the global decision state.

## Future extension

The next safe extension is a weekly volatility baseline (Mon–Fri) feeding decision.options_context.volatility.level_assessment. That baseline should be evidence-backed before enabling high/low language.
## Structural zones (v1)

Key levels are no longer generated as a nearest-strike ladder. The engine selects real observed strikes from multi-expiration GEX concentrations, applies a magnitude threshold, and suppresses adjacent strikes using the actual observed strike grid. The resulting nodes are then converted from Futures to CFD using the observed basis.

For a live snapshot where the current Futures price was around 4152.8, the stored multi-expiration concentration data showed major nodes at 4160, 4200 and 4225 on the upside and 4150, 4125, 4100, 4075 and 4050 on the downside; these are evidence-derived nodes, not prices created by adding $5. The customer map uses the corresponding CFD-normalized prices.
