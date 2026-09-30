# API SPEC

Status: IMPLEMENTATION IN PROGRESS

## Canonical market endpoints

GET /market/:symbol
GET /market/:symbol/positioning
GET /market/:symbol/oi
GET /market/:symbol/gex
GET /market/:symbol/expiry

Common response envelope:
- symbol
- as_of
- data_age_seconds
- data_quality
- data_status
- source
- dataset_version
- calculation_version
- data

No endpoint recalculates GEX/OI. Endpoints expose canonical MarketState/read-model values.

Missing canonical database rows return DATA_UNAVAILABLE rather than synthetic values.

Production adapter to Supabase is intentionally blocked until the correct target project identity is verified.
