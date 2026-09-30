# PRICING MODEL

Status: HYPOTHESIS — NOT OPTIMIZED

## Tiers

FREE
- delayed/limited market overview
- limited news summaries
- limited history
- no API

PRO
- core GOLD intelligence
- OI/GEX/DEX
- daily brief
- limited alerts
- standard history

ADVANCED
- multi-market positioning
- deeper expiry/history
- scenario analysis
- higher alert budget
- API-lite access

TEAM
- shared organization
- multiple seats
- shared watchlists
- audit/administration
- higher API quotas

API
- machine-readable market intelligence
- usage-based quota
- contractual support for larger clients

## Feature-value matrix

| Capability | FREE | PRO | ADVANCED | TEAM | API |
|---|---|---|---|---|---|
| Market overview | YES | YES | YES | YES | YES |
| OI | LIMITED | YES | YES | YES | YES |
| GEX | LIMITED | YES | YES | YES | YES |
| DEX | NO | YES | YES | YES | YES |
| News intelligence | LIMITED | YES | YES | YES | YES |
| Scenario engine | NO | LIMITED | YES | YES | YES |
| Historical positioning | NO | LIMITED | YES | YES | YES |
| Telegram alerts | LIMITED | YES | YES | YES | N/A |
| API | NO | NO | LIMITED | YES | YES |

## Pricing math

Monthly gross margin model:

Revenue
− payment fees
− licensed market-data cost
− news-data cost
− AWS
− Supabase
− LLM inference
− storage/egress
− support
= gross profit

gross margin = gross profit / revenue

Do not set final prices until real cost measurements and provider quotes exist.

## Cost controls

Measure per customer:
- LLM calls
- tokens
- API calls
- alert deliveries
- dashboard reads
- market-data allocation
- storage
- support minutes

Use these measurements to set quotas and later pricing.

No guaranteed-return marketing.
