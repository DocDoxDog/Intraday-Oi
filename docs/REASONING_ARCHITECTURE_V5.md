# V5 Reasoning Architecture

## Goal
Make the market analysis read like a good human analyst without pretending the LLM is the source of truth.

**Core loop:** `FACT → WHY → CONFLICT → NEXT EVENT → INVALIDATION → ACTION`

The LLM is an explanation layer. Deterministic engines own numbers, levels, state and execution gates.

## Repository research → design decisions
- **FinMem**: layered memory is useful; each snapshot should be interpreted in context instead of as an isolated prompt.
- **TradingAgents**: role separation and bullish/bearish debate are useful, but deterministic financial math must remain outside the model.
- **TradingAgents-GUI**: progress, decision cards, reports and diagnostics make complex agent work understandable.
- Finance reasoning benchmarks: point-in-time causality, future-shock tests, purged/embargoed validation and adversarial checks are more important than confident prose.

## V5
1. Evidence Ledger — every claim points to evidence.
2. Reasoning Ladder — WHAT → WHY → CONFLICT → NEXT → INVALIDATION → ACTION.
3. Scenario-first plan — never emit a naked BUY/SELL.
4. Evidence strength — use CONFIRMED / CONDITIONAL / WAIT / DATA_INSUFFICIENT instead of fake probabilities.
5. Human-readable output — concise summaries, not hidden chain-of-thought.

### Scenario contract
LONG: break → acceptance → retest → confirmation.
SHORT: break → acceptance → retest failure → confirmation.
WAIT: no trigger, conflicting evidence, stale data or insufficient risk geometry.

Entry/SL/TP remain owned by the deterministic trade-plan engine.

## Dashboard V5
The first screen should answer:
> **What is happening? Why? What must happen next? Where is the invalidation?**

Order:
1. Current price + freshness
2. One-line Market Read
3. Why now — strongest evidence
4. Conflict/risk
5. LONG vs SHORT scenarios
6. Gamma/OI
7. Key levels
8. Detailed trade plan
9. Raw/dev evidence

The existing dashboard already has strong Action Zones, Gamma, Levels and four-route plans. V5 adds the missing reasoning bridge.

## Engineering gates
- No new price number from the LLM.
- Scenario levels must exist in deterministic evidence.
- Missing values stay UNKNOWN/—.
- No live order execution.
- Point-in-time timestamps remain mandatory.
- V5 runs beside V3/V4 until replay/OOS gates pass.
