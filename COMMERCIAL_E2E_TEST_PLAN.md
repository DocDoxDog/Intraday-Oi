# COMMERCIAL E2E TEST PLAN

Status: NOT RUN

## Core path

Licensed source
→ raw ingestion
→ canonical contract
→ OI/Greeks/GEX/DEX
→ MarketState
→ News
→ Analysis
→ Scenario
→ AlertPolicy
→ customer entitlement
→ Telegram
→ Vercel
→ API

## Customer path

signup
→ organization provisioning
→ membership
→ subscription state
→ entitlement
→ market access
→ API key
→ API request
→ usage event
→ alert delivery
→ feedback

## Required negative tests

- future OI rejected for historical decision
- unknown contract identity rejected
- invalid/expired API key rejected
- revoked API key rejected
- cross-organization access rejected
- disabled entitlement rejected
- disabled market access rejected
- rate limit exceeded rejected
- stale/incomplete MarketState not customer-visible
- unsupported AI number rejected
- unsupported scenario level rejected
- unlicensed news source not customer-distributed
- duplicate story does not create second Telegram message
- update edits existing Telegram message
- /trade remains disabled

## Exit gate

All positive and negative paths must run against a non-production environment
with real auth, database, canonical data fixtures and a Telegram test bot before
commercial production launch.
