# FLOW INTELLIGENCE V1 — SYSTEM DESIGN

## Objective

Turn Intraday-Oi from a snapshot analyst into a time-aware Market Intelligence engine.

RAW → CANONICAL → DERIVED → STATE → STRUCTURE → EVENT → PATH → OUTCOME → LEARNING

## Data domains

Market: market_bars, market_state_snapshots
Options: options_flow_snapshots, option_strike_observations, oi_flow_events, oi_migration_events, gex_history
Structure: structural_nodes, structural_transitions
Events: market_events, market_event_outcomes
News/macro: news_announcements, news_items, news_events, economic_events, news_event_intelligence
AI governance: llm_analysis_runs, existing LLM gateway/verifier/telemetry
Retrieval: market_event_documents + pgvector

## Node flow

N0 Source/entitlement
→ validate source identity, freshness and license.

N1 Raw ingestion
→ preserve source-backed raw information; LLM is never source of truth.

N2 Time alignment
→ keep event_time, published_at, detected_at, retrieved_at and as_of distinct.

N3 Canonicalization
→ normalize instrument, event, indicator, strike, expiry, timezone and session.

N4 Derived analytics
→ deterministic IV, RV, OI, GEX, DEX, Vanna, Charm, skew, term structure, expected range and technical state.

N5 Market state
→ one time-stamped state with evidence references and data quality.

N6 Structural map
→ real nodes selected by global concentration + local prominence + distance + expiry scope.

N7 Transition graph
→ HOLD/REJECT, BREAK/ACCEPT, FAILED_BREAK, RECLAIM and CONTINUATION edges.

N8 Event detector
→ actual bars decide touch/break/acceptance/rejection/retest/state change.

N9 News transmission
→ NEWS → SURPRISE/NOVELTY → CHANNEL → CROSS-ASSET RESPONSE → MARKET STATE.

N10 LLM synthesis
→ send a compact evidence packet, not an uncontrolled database dump.

N11 Verification
→ schema validation + evidence-reference validation + deterministic numeric consistency + epistemic-status checks.

N12 Delivery
→ Telegram bundle: MARKET STATE → STRUCTURAL PATH → EVENT/NEWS → TRADE PLAN. Dashboard remains analysis-first and does not expose the Telegram trade-plan layer.

N13 Outcome
→ T+1/5/15/30/60 outcomes, MFE, MAE, next-node hit and path completion.

## LLM context packet

The model should receive:
as_of, current_price, data_quality, market_state, options_state, volatility_state, macro_state, news_events, structural_nodes, structural_transitions, recent_events, evidence_ledger.

Do not send thousands of raw rows when a small deterministic evidence packet can represent the same state.

## Retrieval

pgvector historical-event similarity is supporting evidence only. It never overrides time, source authority, point-in-time availability or current state.

## Database security

Research/system tables use RLS, server-side service_role access and explicit grants. Event/outcome records are append-first and carry versions/idempotency keys.

## Telegram

Telegram is a delivery surface, not the decision engine. Keep messages compact; use deterministic chunking and HTML/entities. Inline buttons can navigate to path/evidence/full OI-Gamma/status. The Bot API limits text messages to 4096 characters after entity parsing.

## Scientific loop

feature → hypothesis → event → benchmark → OOS → walk-forward → outcome

Never turn a plausible narrative into a directional score without validation.
