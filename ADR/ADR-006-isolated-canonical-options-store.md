# ADR-006 — Isolated Canonical Options Store Namespace

Status: ACCEPTED — Phase 4 amendment

## Context

The verified Supabase target is mwqmxxipgdhbcmwoqueg (cph dashboard). The target database already contains public.instruments with a different schema. Replacing or altering that shared table during Phase 4 would violate the additive migration rule and could affect unrelated production systems.

## Decision

Keep the logical canonical contract model defined by quant/contracts.py, but materialize Phase 4 physical tables under public.oi_core_*: dataset_versions, raw_market_data, instruments, futures, expirations, strikes, options, option_quotes, option_trades, option_oi, greek_observations, gex_snapshots, dex_snapshots, market_states.

This is a physical namespace decision, not a second logical data model.

## Security

RLS is enabled on all canonical tables. A follow-up migration revokes anon and authenticated table privileges. Server-side services use the service role; browser clients do not receive it.

## Consequences

Positive: no destructive collision with the existing CPH schema; canonical store can be validated independently; rollback does not require altering shared legacy tables.

Trade-off: legacy and canonical physical tables coexist during migration; legacy-to-canonical adapters remain until full source ingestion and parity are validated.

## Gate

Do not mark Canonical Data or MarketState production-ready until source ingestion writes canonical raw/contracts/OI observations, availability/publication timestamps are authoritative, canonical MarketState rows are valid and persisted, and PIT/OOS/E2E gates pass.
