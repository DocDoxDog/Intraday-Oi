# GEX PARITY REPORT

Status: PARITY TESTED
Date: 2026-10-01

## Engines

- Legacy A: src/gex.py compatibility path
- Legacy B: DocDoxDog/Ai-trader ai_gold/data/options/gex.py
- Canonical: quant/exposure/gex.py

## Actual parity run

Legacy B source was obtained from the connected GitHub repository and executed against the canonical engine in an isolated test harness.

Coverage:
- symbols: GC, SI, CL, ES, NQ
- scenarios: normal volatility / 14 DTE; high volatility / 3 DTE; expiration-near / 1 DTE
- option sides: CALL and PUT
- comparisons: 30
- result: 30/30 mathematical comparisons within tolerance
- max absolute difference observed: approximately 2.33e-10

The differences are floating-point representation level and not economically material in the tested fixtures.

## Legacy A

The legacy Intraday-Oi import path is now a compatibility facade to the canonical engine. Therefore its parity is exact by construction and is covered by regression tests.

## DEX

Legacy A and Legacy B do not implement DEX. DEX is therefore NOT_COMPARABLE rather than fabricated. Canonical DEX is tested independently.

## Important limitation

The parity fixtures are deterministic synthetic inputs. They validate implementation consistency, not market-data correctness, dealer positioning or predictive power.

Still required before GEX promotion:
- validate source gamma units
- validate authoritative GC multiplier
- validate full multi-expiry aggregation
- validate production PIT data
- validate against exchange/vendor reference outputs where entitlements permit
