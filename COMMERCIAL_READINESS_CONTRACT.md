# COMMERCIAL READINESS CONTRACT

## Release decision

The release controller is fail-closed.

Required gates:
1. data_rights
2. source_timestamps
3. canonical_market_state
4. ci_green
5. ai_trader_baseline
6. tenant_e2e
7. customer_channel_e2e
8. aws_runtime
9. payment_approval
10. legal_regulatory
11. oos_walkforward
12. paper_gate
13. load_test

A missing gate is a failure. Any state other than PASS is a failure.

LIVE_TRADING_ENABLED=true is always a failure during this phase.

## Evidence contract

Each PASS should carry:
- state=PASS;
- evidence_ref;
- executed_at;
- commit_sha;
- environment;
- operator or automated job identity;
- limitations/notes.

Never convert NOT_VERIFIED, PENDING, BLOCKED or LEGAL_REVIEW_REQUIRED directly to PASS.

## Rollback contract

Every promotion requires:
- previous known-good commit;
- feature flags/kill switches;
- database rollback or forward-fix plan;
- service restart procedure;
- customer communication path;
- restore/rollback drill evidence.
