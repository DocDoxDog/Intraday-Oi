# SECURITY AUDIT

Status: AUDIT COMPLETE

## P1 findings

1. Telegram authorization is incomplete in the inspected OI code.
Hardcoded recipient IDs exist. No mature inbound RBAC command layer is present.

2. Trade logic is embedded in notification code.
Telegram/LINE build direction and execution levels. This violates separation of concerns and can turn messaging into an unvalidated signal source.

3. Operational chat identifiers are stored in migration seed data.
Move access control to managed configuration/admin workflows.

4. Support workflow contains bank-account information in repository source.
Move configurable support content out of source control.

5. Supabase service role is the write credential.
Keep it server-only. Vercel browser/client must never receive it.

6. QuikStrike session URL and qsid can be operationally sensitive.
Do not log or expose session identifiers/cookies.

7. Persistence is not a single transaction.
Screenshot, snapshot and intelligence writes can partially succeed.

8. AI-Trader research JSONL is local and not a canonical shared data store.

## P2 findings

- vendor page selectors brittle
- missing centralized rate limits
- missing full pipeline audit-log schema
- no completed E2E security proof in this audit

## Secret baseline

Never expose:
SUPABASE_SERVICE_ROLE_KEY
TELEGRAM_BOT_TOKEN
CME/QuikStrike credentials/session state
GEMINI_API_KEY
MT5_PASSWORD

Use server-side secrets and least privilege.


## Phase 4 security verification — 2026-10-01

- Verified target Supabase project: mwqmxxipgdhbcmwoqueg (cph dashboard), ACTIVE_HEALTHY.
- Canonical options store consists of 14 oi_core_* tables.
- RLS is enabled on all 14 canonical tables.
- SQL privilege verification after canonical_store_server_only shows only service_role remains for the canonical tables; anon/authenticated are not granted table privileges.
- Canonical MarketState writer is server-side and fail-closed for INCOMPLETE/UNAVAILABLE states or missing version metadata.
- Security status remains FAIL for the whole system because the database still has existing advisor findings and full production authorization/E2E verification is incomplete.
