# Canonical Options Intelligence

`Intraday-Oi` is the authoritative options-intelligence layer for downstream trading systems.

## Responsibilities

- ingest QuikStrike/CME-derived observations
- preserve raw OI, ΔOI, IV, Greeks and source timestamps
- calculate deterministic GEX
- publish multi-expiry structure
- expose explicit model/version provenance
- reject the interpretation of missing or stale fields as fresh numeric facts

## Canonical boundary

`src/canonical_options.py` publishes `raw_series.canonical_options`.

The contract contains:
- instrument and source identity
- expiration code, DTE, expiry weight and optional expiry timestamp
- independent freshness for OI, IV and quote data
- GEX value, convention, model and model version
- per-strike OI, ΔOI, IV, delta, gamma and GEX
- data-quality flags

Missing values remain `null`. Stale values are marked `STALE`; they are never replaced with zero.

## GEX

GEX is model-derived, not an observed market fact.

Current explicit convention:
- model: `dealer_short_all`
- version: `canonical-gex-v2`
- call GEX positive
- put GEX negative
- unit: USD per 1% underlying move

A downstream system must display the model/version when presenting GEX-derived levels.

## Expiry

DTE is preserved as fractional when available. `expiry_weight` is a deterministic bounded aggregation/display weight and is not a directional trading signal.

## Flow limitations

ΔOI does not identify aggressor side by itself. `oi_intelligence.py` therefore labels flow hypotheses as hypotheses and keeps limitations explicit. It must not be treated as trade execution evidence without option volume, bid/ask or transaction-level evidence.

## Downstream

AI-Trader should consume `canonical_options` rather than reimplementing GEX. Price/basis, technical regime, risk and execution remain outside this repository.
