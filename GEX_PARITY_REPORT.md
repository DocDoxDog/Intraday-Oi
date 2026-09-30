# GEX PARITY REPORT

Status: EXECUTED IN CI FOR CURRENT PHASE-4 COMMIT
Scope: GC, SI, CL, ES, NQ deterministic synthetic regression fixtures

## Engines

- Legacy A: src/gex.py compatibility facade over canonical engine
- Legacy B: DocDoxDog/Ai-trader ai_gold/data/options/gex.py
- Canonical: quant/exposure/gex.py

## Test matrix

Each symbol is checked in:
- normal volatility / 14 DTE
- high volatility / 3 DTE
- expiration-near / 1 DTE
- missing gamma/IV case
- zero OI case

Parity dimensions:
- row-level GEX
- call/put sign
- contract multiplier
- strike-level result
- total result
- calculation consistency

DEX:
Legacy A and Legacy B do not implement DEX, so DEX parity is NOT_COMPARABLE. Canonical DEX is tested independently.

## Interpretation

The parity tests are mathematical regression tests using synthetic inputs, not market-data validation.

Promotion still requires:
1. parity CI success on the canonical implementation,
2. source gamma unit validation,
3. GC contract multiplier validation,
4. multi-expiry contract-universe validation,
5. PIT tests.

This file must not be read as evidence of dealer positioning correctness.
