# OI / GEX Intelligence — Project Audit
Date: 2026-10-01
Branch: research/oi-gex-intelligence-foundation
Repository: DocDoxDog/Intraday-Oi
AI integration repository: DocDoxDog/Ai-trader

## Scope
Audit only. No production trading logic was changed in this phase.

## Current Architecture
QuikStrike scraper -> parser -> spot/technical enrichment -> historical Supabase context -> OI positioning -> OI intelligence -> Gemini narrative -> Supabase -> Telegram/LINE.
Existing GEX is calculated in src/gex.py and can be emitted by the parser/main pipeline.
Structured OI intelligence is persisted through Supabase migration 008.

## Existing Data Sources
- CME QuikStrike / Open Interest view: strike-level OI, Greeks/IV where supplied, expiry metadata.
- Twelve Data: XAU/USD spot and OHLC technical context.
- Supabase: options_flow_snapshots plus OI intelligence tables.
- Gemini: narrative generation only; it is currently downstream of deterministic calculations.

## Existing Code
- src/scraper.py: QuikStrike acquisition.
- src/parser.py: normalization into strike_rows/raw_series.
- src/gex.py: Black-76 gamma fallback and signed OI GEX.
- src/oi_positioning.py: current-vs-baseline ΔOI/churn.
- src/oi_intelligence.py: delta exposure, flow labels, nearest-strike migration.
- src/history.py: hour-ago/today/EOD baseline retrieval.
- src/analyze.py: LLM narrative and trade-plan formatting.
- tests/: GEX, OI intelligence and parser tests.
- supabase/migrations/008_oi_intelligence.sql: exposure/flow/migration persistence.
- .github/workflows/oi-intelligence-tests.yml: pytest CI.
- .github/workflows/gex_now.yml: one-shot current GEX calculation.

## Current Data Model
The current schema is snapshot-centric. It stores raw_series JSONB and selected exposure aggregates. It does NOT yet provide a canonical contract-master/history-first schema designed for reproducible multi-expiry longitudinal research.

## Current GEX Formula
Current implementation uses:
GEX_per_strike = OI × Gamma × contract_multiplier × F² × 0.01
with calls positive and puts negative under a documented code convention.
This is a dealer-position proxy, not observed dealer inventory.

Gamma is taken from QuikStrike when present; otherwise Black-76 gamma is derived from IV and DTE.

## Current OI Model
Current-vs-EOD baseline produces ΔOI and churn. This is valid as an OI-change measurement when timestamps/baseline are correct. It must not be called traded volume.

## Current Flow Inference
Current classify_flow() can emit NEW_LONG, SHORT_COVER, etc. from OI change plus underlying price change. This is not sufficiently identified to claim the option trade direction or dealer position. These labels must be downgraded to hypotheses unless additional trade-direction/quote evidence is present.

## Current Tests
There are unit tests for:
- Black-76 gamma positivity.
- signed GEX convention.
- IV gamma fallback.
- delta-adjusted exposure.
- unknown flow without price.
- nearest-strike migration.

Coverage is narrow. There are no tests yet for:
- unit consistency against independent numerical references;
- alternative sign conventions;
- multi-expiry aggregation;
- timestamp/publication-time leakage;
- contract mapping/rolls;
- DTE/expiry edge cases;
- missing Greeks/IV behavior;
- data versioning/checksums;
- walk-forward research;
- baseline-vs-OI/GEX predictive comparison.

## Critical Findings
1. GEX sign is hard-coded to call-positive/put-negative in the current engine. It is an assumption and must become a versioned convention.
2. Dealer positioning is not observed. Public OI does not identify which participant holds which side.
3. Current flow labels overstate what OI + price alone can identify.
4. Current migration logic is a nearest-strike redistribution hypothesis, not observed rolling.
5. Current history is not yet a publication-time-aware research dataset.
6. Current QuikStrike pipeline is optimized for operational reporting, not research-grade reproducibility.
7. AI receives deterministic and raw-derived summaries, but no validated positioning state contract exists yet.
8. There is no evidence in the repository yet that OI/GEX adds information over price/volume/volatility baselines.
9. Existing technical indicators must remain separate from the OI/GEX research question to avoid attribution contamination.
10. Existing GEX is suitable as a prototype calculation layer, not yet as a validated trading signal.

## Current Limitations
- Single instrument focus: GC.
- QuikStrike source availability/entitlements may constrain historical depth.
- Current schema is not a canonical option-contract event store.
- Official vs preliminary CME OI timing is not modeled explicitly.
- No dataset version/checksum pipeline.
- No complete hypothesis registry or experiment registry.
- No out-of-sample evidence for the current GEX implementation.

## Unknown / Must Measure
- Historical GC option-chain depth and completeness.
- Exact publication timestamps available for every OI observation.
- Whether current QuikStrike snapshots contain official or preliminary OI.
- Stability of GEX sign assumptions across expiry buckets.
- Incremental predictive value of OI/GEX after price, volume, IV and realized-vol baselines.
- Robustness across expiry, volatility and event regimes.

## Audit Status
RESEARCH FOUNDATION REQUIRED. Do not promote current GEX/flow labels to trading signals.
