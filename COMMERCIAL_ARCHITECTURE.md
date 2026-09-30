# COMMERCIAL ARCHITECTURE

Status: IMPLEMENTATION IN PROGRESS

## Product boundary

AI Market Intelligence is a market-information and scenario-analysis product for CFD traders. It does not accept customer orders, custody funds, or act as a broker.

Core chain:

DATA
→ CANONICAL
→ QUANT
→ MARKET STATE
→ INTELLIGENCE
→ AI ANALYSIS
→ SCENARIO
→ ALERT
→ ENTITLEMENT
→ TELEGRAM / VERCEL / API

## Ownership

DATA/CANONICAL/QUANT: Intraday-Oi
RESEARCH/BACKTEST/OOS/SIGNAL/RISK/EXECUTION: Ai-trader
CUSTOMER/ENTITLEMENT/BILLING: commercial layer
PRESENTATION: Telegram + Vercel
PERSISTENCE: Supabase
ALWAYS-ON WORKERS: AWS

## Hard boundary

Telegram, Vercel and customer APIs never calculate OI/GEX/Greeks.
They consume canonical semantic objects and read models only.

AI never invents numerical market data.
Scenario output is conditional language, not guaranteed outcome language.

Execution remains disabled in the commercial product.

## Data domains

1. Raw licensed/source observations
2. Canonical normalized observations
3. Derived OI/Greeks/GEX/DEX
4. MarketState
5. News/StoryCluster/NewsImpact
6. MarketConfirmation
7. MarketAnalysis
8. ScenarioPlan
9. Alerts and customer delivery
10. Entitlement/usage/audit

## Customer separation

Every customer-owned object carries organization_id.
Server-side entitlement checks are authoritative.
No frontend boolean is trusted for access control.

## Deployment

AWS EC2:
continuous ingestion, processing, intelligence workers, Telegram worker, health monitor

Supabase:
persistent canonical and commercial state

Vercel:
research terminal and customer-facing web application

## Production gates

Commercial production requires data licensing, PIT-safe ingestion, tenant isolation,
AI verification, alert-quality measurement, payment/legal review, observability,
backup/recovery, and E2E tests.
