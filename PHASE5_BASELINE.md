# PHASE 5 BASELINE

Date: 2026-10-01
Status: FROZEN FOR COMMERCIAL PRODUCT WORK

## Repository

Primary: DocDoxDog/Intraday-Oi
Branch: research/oi-gex-intelligence-foundation

User-provided Phase 4 baseline:
642afd824e4cef55a6cc8546e742a418a2894191

Observed branch state at Phase 5 start:
The branch had advanced beyond 642afd8 during Phase 4 follow-up work. The latest Phase 4 status document recorded commit 363107842ae5e0641058f826d796559919cfa9e7. Subsequent Phase 5 work starts from the branch state, not by reverting to 642afd8.

Related repository:
DocDoxDog/Ai-trader
Branch: integration/canonical-market-state
Observed integration commit: 988a419a8d39202e9392e0525e7709e4fef51280

## Runtime

Intraday-Oi:
- CI Python: 3.11
- requirements are version ranges, not fully locked
- web CI uses Node 22
- web package: Next 16.3.7, React 19.2.0, React DOM 19.2.0, TypeScript 5.9.x range

Ai-trader:
- CI Python: 3.12
- requirements-ci.txt is not fully pinned

## Phase 4 quality state

Canonical contracts: FAIL for production promotion (models/tests exist, legacy source identity unresolved)
Canonical OI: FAIL for production promotion (PIT model exists, source publication/availability ingestion incomplete)
Canonical Greeks: PASS on implemented unit tests
Canonical GEX: PASS on implemented unit tests
GEX parity: PASS on executed 30/30 mathematical comparisons
PIT model tests: PASS
MarketState: FAIL for production promotion (no valid persisted canonical state)
AI-Trader integration: FAIL overall because baseline unit CI failed
Telegram: FAIL for production/E2E promotion
Vercel build: PASS in GitHub Actions; production data/API deployment not promoted
Paper trading: FAIL / NOT RUN
E2E: FAIL / NOT RUN
Security: FAIL overall
Live trading: DISABLED

## Supabase

Verified target:
mwqmxxipgdhbcmwoqueg
Project name: cph dashboard
Region: ap-southeast-1
Status at verification: ACTIVE_HEALTHY

Phase 4 canonical tables:
14 public.oi_core_* tables
- RLS enabled on all 14
- anon/authenticated table privileges revoked
- service_role retained
- canonical row counts were 0 at Phase 4 verification

## Vercel

Team:
WiseGon
Team ID: team_P9XEtJGLANXxiFIATp5NPa7E

Known projects include:
cp-hunter (prj_vaRl90KvAqEOzzRXUllcIPPGTYZA)
No separate commercial OI customer product deployment was identified during baseline inspection.

## Legacy preservation

No Phase 5 work may delete:
- src/gex.py compatibility path
- legacy QuikStrike acquisition
- legacy Telegram/LINE delivery
- existing Supabase schemas
- Ai-trader independent research implementation

Removal requires dual-run, comparison, cutover evidence and explicit change record.

## Phase 5 baseline rule

No PASS is granted merely because code exists.
Commercial launch remains blocked until:
- licensed data boundaries are verified
- PIT-safe canonical ingestion is real
- customer tenancy/entitlement isolation is tested
- AI output verifier blocks unsupported claims
- alert quality is measured
- payment/legal/regulatory review is completed for the intended jurisdictions
- E2E and operational recovery are demonstrated

