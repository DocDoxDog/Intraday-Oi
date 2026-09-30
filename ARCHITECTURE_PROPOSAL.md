# ARCHITECTURE PROPOSAL

Status: ARCHITECTURE READY
Date: 2026-10-01

## CURRENT -> PROPOSED

Intraday-Oi:
QuikStrike acquisition + snapshot/reporting
-> Data Engine + acquisition adapters + raw/normalized/PIT observations

Ai-trader:
market features + research + decision + MT5
-> Research + Signal + Risk + AI + Execution

Shared:
two GEX implementations
-> one canonical options quant package

Persistence:
snapshots + JSONL
-> Postgres/Supabase canonical data store; JSONL retained as export/fixture

Telegram:
outbound formatters
-> authenticated command + alert control plane

Vercel:
static dashboard
-> terminal-style frontend + thin API

## TARGET OWNERSHIP

DATA ENGINE
- source adapters
- raw immutable payloads
- normalization
- contract/expiry master
- publication/availability timestamps
- quality checks

CANONICAL QUANT ENGINE
- OI
- ΔOI
- IV/Greeks
- GEX
- DEX
- levels
- exposure metadata

RESEARCH ENGINE
- dataset versions
- hypotheses
- baselines
- experiments
- backtest
- OOS
- walk-forward
- uncertainty

SIGNAL + RISK
- signal state
- costs
- confidence
- NO_TRADE
- risk limits

AI TRADER
- structured-state interpretation
- scenario/risk/action output
- never recompute numeric options metrics

TELEGRAM
- operator commands
- alerts
- chart requests
- acknowledgements
- authenticated control

VERCEL
- dashboard
- thin API
- server-rendered shell

## SINGLE SOURCE OF TRUTH

One canonical package owns GEX/DEX/Greeks/OI calculations. The candidate initial basis is the better-documented Intraday-Oi GEX implementation, but selection is conditional on source-unit validation and cross-repo parity testing.

Every analytic result must preserve:
VALUE
SOURCE
OBSERVATION_TIME
PUBLICATION_TIME
AVAILABILITY_TIME
CALCULATION_TIME
CALCULATION_VERSION
DATASET_VERSION
ASSUMPTIONS
CONFIDENCE
QUALITY

## MIGRATION

1. freeze feature expansion and capture baseline
2. add canonical data schema and adapters
3. parity-test both GEX engines
4. dual-run old and new
5. migrate research to canonical dataset
6. centralize Telegram/alerts
7. build Vercel read models
8. integrate structured positioning state into AI
9. paper trade
10. GC canary, then other instruments
11. remove duplicates only after observation

## RISKS

Vendor UI changes, historical entitlements, preliminary/final OI correction, missing intraday OI, gamma-unit ambiguity, dealer-side non-identification, expiry mapping, cross-source price basis, scheduler overlap, partial writes, secret exposure, AI overinterpretation.

## DECISION

Do not rewrite either repository. Use adapters and a staged migration.
