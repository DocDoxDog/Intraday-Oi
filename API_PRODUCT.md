# API PRODUCT

Status: IMPLEMENTATION IN PROGRESS

## Current customer endpoints

GET /api/v1/market/:symbol
GET /api/v1/gex/:symbol
GET /api/v1/oi/:symbol
GET /api/v1/positioning/:symbol

Authentication:
X-API-Key

API keys are stored as hashes, can be revoked/expired, and are checked against
organization entitlements and market access server-side.

Rate limiting:
per-organization fixed-window in-process guard for the initial single-instance
deployment. Multi-instance production must use a shared limiter.

Every successful market response inherits:
as_of
data_age
data_quality
data_status
dataset_version
calculation_version

Additional product endpoints are reserved for:
news
analysis
plan

They must not return fabricated or placeholder market facts.

## Usage metering

Future request lifecycle:

authenticate
→ entitlement
→ market access
→ rate limit
→ canonical read
→ response
→ usage event

Usage event fields:
api_key_id
organization_id
endpoint
timestamp
status
latency
units

## API security

Never store plaintext API keys.
Never expose service_role to clients.
Never trust frontend entitlement flags.
Use HTTPS/TLS in production.
