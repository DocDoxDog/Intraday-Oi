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

Production target identity is now verified as Supabase project `mwqmxxipgdhbcmwoqueg` (`cph dashboard`). The API read adapter uses `oi_core_market_states` when `CANONICAL_DB_READS=true`. Canonical tables are server-role-only; no browser `service_role` credential is exposed.

Current runtime state remains unavailable until a valid canonical MarketState is ingested.
