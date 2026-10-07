# PHASE 6 — COMMERCIAL READINESS / CONTROLLED BETA

Status: BLOCKED

## Objective

Convert the Phase 5 commercial skeleton into a system that can prove every production prerequisite independently.

Phase 6 does not change canonical GEX/OI math and does not enable live trading.

## 6.0 Deterministic release controller

Implemented:
- machine-readable required gates;
- fail-closed release evaluation;
- explicit LIVE_TRADING disabled rule.

## 6.1 Point-in-time MarketState

Implemented:
- publication_time;
- availability_time;
- ingestion_time;
- future-data rejection;
- stale/incomplete rejection;
- dataset/calculation version requirements;
- data-rights approval requirement.

Still required:
- real GC source with authoritative publication/availability timestamps;
- persisted production MarketState;
- source reconciliation.

## 6.2 Data-rights enforcement

Implemented:
- rights state;
- agreement activation window;
- separate customer display/API/alert/raw-storage permissions.

Still required:
- executed agreements;
- agreement references;
- source-by-source scope review;
- automated rights loading from the evidence ledger.

CME publicly separates internal display/non-display, distribution and derived-data licensing:
https://www.cmegroup.com/market-data/license-data.html
https://www.cmegroup.com/market-data/browse-data/derived-data.html

## 6.3 Customer isolation and E2E

Existing:
- organization/membership/entitlement/API-key gateway;
- RLS and server-only sensitive storage;
- Telegram/Vercel/API paths.

Required:
- non-production Supabase Auth tenant fixture;
- organization A/B isolation;
- subscription -> entitlement -> market-access E2E;
- revoked/expired API-key tests;
- Telegram account-link E2E;
- Vercel authenticated terminal E2E.

## 6.4 Runtime

Required:
- AWS EC2 deployment;
- secret injection;
- health/readiness/metrics;
- log aggregation;
- restart/recovery drill;
- backup/restore drill;
- rollback drill.

## 6.5 Commercial provider and legal review

Required:
- payment-provider written eligibility;
- webhook signature/idempotency test;
- refund/chargeback procedure;
- tax/accounting treatment;
- Thai product/legal classification;
- target-jurisdiction feature controls;
- market-data/news licensing sign-off.

Paddle's current AUP excludes investment/financial advice and trading signals/strategies.
Stripe states that restricted-business rules apply in Thailand and some business categories require approval.
Thailand SEC announced a public consultation on 17 September 2026 concerning investment advice through media, including online channels.

## 6.6 Validation

Required:
- latest Phase 5 full CI green;
- Ai-trader baseline root-cause resolution;
- positive/negative commercial E2E;
- 100/500/1,000-user load tests;
- OOS/walk-forward for signal-like components;
- paper-trading gate.

## 6.7 Controlled beta review

Only after the objective gates are PASS:
- small non-public test cohort;
- live trading remains disabled;
- measure alert precision, suppression, latency, API errors, tenant isolation, entitlement correctness and support incidents;
- maintain feature-level kill switches.

Paid access remains gated by legal, provider and licensing approval.

## Exit

Commercial production review can start only when all REQUIRED_GATES in commercial.release_gate are PASS.
