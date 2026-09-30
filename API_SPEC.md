# API SPEC

Status: ARCHITECTURE READY

## Response envelope

    {
      "symbol": "GC",
      "as_of": "ISO-8601",
      "data_age_seconds": 0,
      "source": "cme_quikstrike",
      "data_status": "VALID",
      "model_version": "gex-vX",
      "dataset_version": "dataset-X",
      "data": {}
    }

## Endpoints

GET /api/market/:symbol
GET /api/options/:symbol
GET /api/options/:symbol/chain
GET /api/oi/:symbol
GET /api/gex/:symbol
GET /api/exposure/:symbol
GET /api/regime/:symbol
GET /api/levels/:symbol
GET /api/flow/:symbol
GET /api/history/:symbol
GET /api/signals/:symbol
GET /api/research/:symbol
GET /api/alerts
GET /api/system/status

## Rules

- filtering server-side
- no full-chain payload unless requested
- heavy calculations precomputed
- PIT-safe as_of queries
- version metadata on every analytic response
- no frontend secrets
