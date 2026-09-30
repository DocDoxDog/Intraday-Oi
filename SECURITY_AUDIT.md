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
