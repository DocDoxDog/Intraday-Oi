# RUNBOOK

Status: ARCHITECTURE READY

## Normal path

source health
-> ingest
-> contract/schema validation
-> raw store
-> PIT observation
-> quant
-> derived persistence
-> signal/risk
-> Telegram/Vercel

## Failure states

DATA_UNAVAILABLE:
do not fabricate; expose stale/unavailable state.

GEX_UNAVAILABLE:
OI can remain available if independently valid; required positioning signals become NO_TRADE.

DATA_STALE:
do not create new signal.

PIPELINE_FAILURE:
retry with backoff, persist failure, dead-letter after threshold.

TELEGRAM_FAILURE:
queue/retry without stopping quant.

DASHBOARD_FAILURE:
Telegram continues.

DATABASE_FAILURE:
retry/backoff and recover; never silently drop data.

## Incident evidence

pipeline_run_id
source status
last ingest
data age
contract/expiry
row counts
checksum
dataset/version
quant version
DB/API/Telegram failures

## Trading incident

kill switch
reconcile positions/orders
preserve evidence
verify risk state
only then consider re-enabling.
