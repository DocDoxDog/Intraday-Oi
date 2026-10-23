# Graphify Integration

Graphify is development-time architecture tooling, not a production market-data dependency.

## Workflow

Run it against the branch being audited before architecture changes.

Useful queries:
- Trace QuikStrike scrape → parser → deterministic analysis → LLM → verification → Telegram.
- Which modules calculate OI, GEX, levels and trade plans?
- Where does LLM output enter?
- Which modules can mutate deterministic values?
- Find duplicated decision logic.
- Find every consumer of raw_series.
- Trace producers and consumers of oi_change_call, oi_change_put, volumeCall, volumePut and vol.
- Trace Max Pain, Pinning, gamma flip, call wall and put wall.

## Evidence boundary

EXTRACTED means directly supported by source material.

INFERRED means inferred by Graphify. It must not become a financial fact without source verification.

Keep graphify-out out of the production runtime and market-data schema.
