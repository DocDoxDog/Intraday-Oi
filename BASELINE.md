# BASELINE

Status: BASELINE CAPTURED BEFORE PHASE 4 CODE MIGRATION
Capture date: 2026-10-01

## Repository state

Primary repository:
DocDoxDog/Intraday-Oi

Branch:
research/oi-gex-intelligence-foundation

Commit immediately before Phase 4 implementation:
f1776151e6f2a164fffb447fc28c0c7db4cdfebd

Ai-trader reference:
DocDoxDog/Ai-trader
branch: main
Audited source includes independent GEX engine and research/decision stack.

## Runtime / dependency baseline

Intraday-Oi CI Python:
3.11 (GitHub Actions workflow)

Intraday-Oi declared dependencies:
playwright>=1.45.0
supabase>=2.5.0
python-dotenv>=1.0.0
requests>=2.31.0
matplotlib>=3.8.0

Important: dependency versions are ranges, not a lockfile. No resolved production environment manifest is stored in the repository.

Ai-trader Python requirement:
>=3.12

Ai-trader declared dependencies are unpinned except pydantic>=2:
MetaTrader5, fastapi, pydantic>=2, pydantic-settings, numpy, polars, pyarrow, duckdb, scipy, statsmodels, scikit-learn, pytest, httpx.

## Database baseline

The repository contains migrations 001-008 for:
- options_flow_snapshots
- screenshot storage/columns
- DTE
- customers
- CFD/technical context
- OI intelligence tables

The repository .env.example points to Supabase project ref mwqmxxipgdhbcmwoqueg (labelled cph dashboard), while the README describes an OI-intraday project. Current connected Supabase projects do not expose a project named OI-intraday. Therefore the deployed target database identity is NOT treated as verified.

This is a blocker for applying the canonical schema to production. Migration SQL will be prepared in the repository, but no destructive/live database migration will be claimed as applied without verified target project identity.

## Current GEX baseline

Intraday-Oi:
- file: src/gex.py
- calculation version: gex-v2
- default sign convention: DEALER_SHORT_PUBLIC
- declared unit: USD per 1% underlying move
- multiplier default: 100 for GC
- source gamma used when available; Black-76 fallback from IV otherwise
- dealer_position_observed=false

Ai-trader:
- file: ai_gold/data/options/gex.py
- calculation version: black76-gex-v1
- independent implementation
- same broad GEX dimensional structure but separate interface/version

No historical production GEX output file is committed as a reproducible fixture. Therefore baseline preserves implementation/version metadata and test fixtures, but does not invent a market observation.

## Current OI baseline

Intraday-Oi:
- QuikStrike image-map/legacy Highcharts acquisition
- strike-level call/put OI retained in raw_series
- ΔOI may be derived from prior snapshot
- selected expiry policy rather than full option surface
- history keyed by captured_at in Supabase

Known limitations:
- publication_time / availability_time absent from legacy snapshot model
- EOD/preliminary/official state not represented
- no full canonical option master

## Current AI-Trader baseline

- FeatureEngine computes price/ATR/trend/microstructure features.
- AutonomousGoldBrain calls FinalBrain with macro_score=0.0 and positioning_score=0.0.
- Meta prediction is explicitly documented as a baseline placeholder, not a trained/calibrated profitability model:
  expected_r = max(0, 2.5 * p - 1.0)
- DecisionEngine fails closed when no validated analyzers are present and currently does not promote an ensemble.
- Execution exists but must remain downstream of risk/research gates.

## Current backtest baseline

No reproducible GC OI/GEX out-of-sample backtest artifact is present in the inspected repository state.

The Ai-trader repository contains research/evaluation/walk-forward infrastructure, but this baseline does not claim a backtest result without an executed dataset/run.

## Baseline test state

Existing tests were present in both repositories. Before Phase 4 implementation, tests were not executed in this environment. Therefore:
- QA PASS: NO
- Production Ready: NO

Phase 4 rule:
legacy implementations remain available until parity/regression tests are executed and unexplained differences are resolved.

## Baseline preservation rule

Any later change to a core formula, unit, multiplier, timestamp policy or contract identity must reference this baseline and explain numerical differences in CHANGELOG.md / parity reports.
