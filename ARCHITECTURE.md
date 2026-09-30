# ARCHITECTURE

Status: IMPLEMENTATION IN PROGRESS

Phase 4 physical storage amendment: the target Supabase database already contains a shared `public.instruments` table with a different schema. Canonical Phase 4 storage therefore uses an isolated `public.oi_core_*` namespace. This preserves one logical canonical model while avoiding destructive collision with legacy/shared tables.

## Runtime boundaries

1. DATA ENGINE
Long-running Python workers handle source ingestion, normalization, contract master, PIT timestamps and quality.

2. CANONICAL QUANT ENGINE
Pure deterministic Python. No network, Telegram or frontend dependencies.

3. RESEARCH ENGINE
Owns datasets, hypotheses, experiments, baselines, OOS and walk-forward.

4. SIGNAL/RISK
Owns signals, NO_TRADE, confidence, transaction costs and limits.

5. AI TRADER
Consumes structured state and passes through validated gates.

6. SERVICES
Telegram, alerts, API orchestration.

7. WEB
Vercel dashboard/API only.

## Deployment shape

CME/providers
 -> Data workers
 -> Supabase/Postgres
 -> Quant workers
 -> Research/Signal
 -> AI Trader
 -> Telegram + Vercel + paper/live execution

Vercel is not the home for continuous ingestion or heavy backtests.

## Source hierarchy

1 exchange/provider raw data
2 canonical normalized observations
3 deterministic quant output
4 research features
5 signal state
6 AI interpretation
7 presentation

Lower layers cannot overwrite higher-layer numeric truth.
