# PAYMENT CONTRACT

Status: RESEARCH_ONLY — NO PRODUCTION PROVIDER INTEGRATED

The application uses an internal subscription state machine independent of the payment provider.

Provider webhook flow:

PAYMENT PROVIDER
→ signature verification
→ provider_event_id idempotency check
→ subscription mapping
→ commercial.subscriptions
→ commercial.entitlements
→ audit log
→ customer notification

Required provider event fields:

provider
provider_event_id
event_type
signature_valid
payload_hash
received_at
processed_at
status

Never trust a client-side subscription flag.

Provider selection remains subject to PAYMENT_RESEARCH.md and written eligibility/commercial review.
