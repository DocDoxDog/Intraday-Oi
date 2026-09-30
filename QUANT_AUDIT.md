# QUANT AUDIT

Status: AUDIT COMPLETE

## Black-76 gamma

Current implementations use Black-76 for options on futures:

d1 = [ln(F/K) + 0.5*sigma^2*T] / (sigma*sqrt(T))
gamma = exp(-rT) * phi(d1) / (F*sigma*sqrt(T))

Inputs requiring validation:
F, K, IV units, T convention, expiry timestamp, risk-free rate, source gamma units.

Current code uses T = DTE/365. This is a convention requiring source/expiry validation, not an automatically correct truth.

## GEX

Current formula:

GEX = gamma * OI * multiplier * F^2 * 0.01 * sign

Declared unit:
USD per 1% underlying move

The formula is dimensionally plausible, but production validation must confirm:
- source gamma units
- whether gamma is already normalized/per contract
- GC multiplier
- futures vs spot basis
- expiry aggregation scope
- sign convention

## Duplicate engines

Intraday-Oi src/gex.py:
- gex-v2
- explicit gamma source
- explicit dealer-position-observed flag
- explicit sign assumption

Ai-trader ai_gold/data/options/gex.py:
- black76-gex-v1
- separate sign registry and dataclasses

One must become canonical. No production cutover before parity tests.

## Sign convention

DEALER_SHORT_PUBLIC maps call positive / put negative. This is a model assumption, not observed dealer inventory.

Required research variants:
1. call+ / put-
2. reverse sign
3. gross absolute gamma
4. later flow-aware / participation-calibrated specification

## Walls and gamma flip

Current call_wall and put_wall are largest modeled GEX concentrations under the selected sign convention. gamma_flip is a cumulative zero crossing on the strike grid.

These are modeled levels, not guaranteed support/resistance. Current acquisition is also effectively one selected expiry, so it does not equal a full-book market gamma flip.

## DEX

Current DEX is OI * Delta * multiplier. The future engine must preserve delta source, multiplier, sign, unit and expiry scope.

## OI and flow

OI is outstanding contracts. ΔOI is a difference between valid observations.

Current flow labels NEW_LONG / SHORT_COVER / LONG_LIQUIDATION are too strong when derived only from OI delta and underlying price. Rename toward:
BUILD, UNWIND, ROLL, SHIFT, DECAY, UNKNOWN.

## Current migration issue

oi_migration.py style logic pairs decreases/increases on existing strikes using nearest-strike matching. New strikes absent from the previous snapshot are not represented as independent increases, and the result is explicitly a low-confidence hypothesis. It should never be presented as observed transfer of positions.

## Quant tests required

Black-76, units, multiplier, IV conversion, DTE boundaries, sign variants, source-vs-derived gamma, multi-expiry aggregation, gamma flip interpolation, duplicate contracts, expired contracts, PIT availability, determinism.

Existing tests have not been executed in this audit session.
