# DATA FLOW

Status: AUDIT COMPLETE

## Current

Source -> URL/session -> QuikStrike scrape -> parser -> OI/GEX enrichment -> optional Twelve Data -> Gemini -> Supabase -> Telegram/LINE.

The current source is a QuikStrike web surface, not a fully entitled direct historical CME DataMine ingestion path.

## Information classes

OBSERVED:
- strike
- call/put OI when supplied
- option prices/settlement fields when supplied
- vendor IV/Greeks when supplied
- source futures reference price
- source timestamps when exposed

DERIVED:
- ΔOI from valid prior OI observation
- DEX
- GEX
- cumulative GEX
- gamma-flip approximation
- concentration/z-score features
- regime features

INFERRED/HYPOTHESIS:
- flow intent
- strike migration
- dealer positioning
- expected hedging behavior

ASSUMED:
- fixed public dealer-sign convention
- selected expiry scope
- certain source-to-spot transformations

LLM output is interpretation only.

## Point-in-time contract

Every option observation must carry:
trade_date
event_time / observation_time
publication_time
availability_time
ingestion_time
calculation_time
timezone
source
source_file or endpoint
source_version
dataset_version

For a decision at decision_time:
availability_time <= decision_time

Official corrected data must not silently replace the value available at the simulated decision time.

## Target flow

SOURCE
 -> RAW IMMUTABLE
 -> NORMALIZED
 -> CANONICAL CONTRACT
 -> PIT OBSERVATION
 -> OI / GREEKS
 -> GEX / DEX
 -> POSITIONING / REGIME
 -> FEATURES
 -> RESEARCH / SIGNAL
 -> AI / TELEGRAM / VERCEL

Dashboard and Telegram consume canonical derived views. They must not calculate their own GEX, walls or gamma flip.
