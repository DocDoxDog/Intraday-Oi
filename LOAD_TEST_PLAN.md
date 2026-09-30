# LOAD TEST PLAN

Status: NOT RUN

## Targets

100 users
500 users
1,000 users

## Workloads

1. News burst:
   100-1,000 customer notification evaluations during a short burst.

2. Market update burst:
   repeated MarketState reads for GC and later multi-market expansion.

3. Telegram burst:
   concurrent commands and callback interactions.

4. API burst:
   authenticated X-API-Key reads across market, GEX, OI and positioning.

5. Intelligence burst:
   clustered-news ingestion with anti-spam checks.

## Metrics

p50/p95/p99 latency
error rate
429 rate
CPU/memory
DB connection usage
Supabase query latency
Telegram delivery latency
alert dedup rate
analysis cache hit rate
LLM calls/day
LLM token usage
LLM cost
data freshness lag

## Acceptance examples

These are engineering targets to be measured, not historical claims:
- no correctness regression under sustained load
- no cross-tenant data leakage
- no duplicate story delivery beyond the dedupe contract
- stale data blocks customer delivery when configured
- API rate limiting behaves deterministically
- worker recovery after process restart is observable
- database remains within connection/query budgets

Exact numeric SLOs should be set from measured baseline and provider capacity tests.
