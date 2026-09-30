# GEX PARITY REPORT

Status: EXECUTION PENDING
Scope: GC, SI, CL, ES, NQ synthetic regression fixtures

## Engines

- Legacy A: src/gex.py (compatibility path)
- Legacy B: DocDoxDog/Ai-trader ai_gold/data/options/gex.py
- Canonical: quant/exposure/gex.py

## Required cases

normal day | high volatility day | expiration day | missing data | zero OI | zero gamma

The current automated parity fixture uses deterministic synthetic observations. It is a test fixture, not market data.

## Comparison dimensions

- row-level GEX
- strike aggregation
- expiry aggregation
- total GEX
- DEX availability

Legacy B currently implements GEX only; DEX parity is therefore explicitly NOT_COMPARABLE rather than fabricated.

## Promotion rule

Canonical GEX cannot be promoted until:
1. Legacy A parity has no unexplained material difference.
2. Legacy B parity has no unexplained material difference.
3. Source gamma unit and GC multiplier are validated.
4. Multi-expiry aggregation is tested against a canonical contract universe.
5. PIT availability tests pass.

This report must be updated with actual test results after CI execution. No PASS is claimed here.
