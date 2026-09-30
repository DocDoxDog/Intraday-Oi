# GEX Methodology
Status: research specification, not trading validation.

## Core measurement
For a futures option:
Gamma is the second derivative of option value with respect to futures price. For Black-76:
gamma = exp(-rT) * phi(d1) / (F * sigma * sqrt(T))
where d1 = [ln(F/K) + 0.5 sigma²T] / (sigma sqrt(T)).

A common dollar-gamma normalization for a 1% move is:
GEX = OI × Gamma × Multiplier × F² × 0.01 × sign.

The 0.01 factor means the reported unit is currency exposure per 1% move.

## GC contract
GC futures contract size is 100 troy ounces. The canonical multiplier must come from the contract master, not a scattered constant.

## Sign conventions
The engine must support at least:
- C_A: calls +, puts -
- C_B: calls -, puts +
- C_C: unsigned/gross gamma
- C_D: flow-aware sign only when sufficient trade-direction evidence exists

C_A must never be described as observed dealer positioning. It is a signed-OI proxy.

## Gamma source priority
1. Exchange/vendor supplied gamma with provenance.
2. Independently recomputed Black-76 gamma from observed IV, F, K, DTE and rate.
3. NULL if required inputs are unavailable.

Derived gamma must carry gamma_source=derived_black76 and calculation_version.

## Aggregation
Compute:
- per strike
- per expiry
- expiry bucket
- total active chain
- call component
- put component
- gross absolute GEX
- net signed GEX under each convention.

## Gamma flip
Gamma flip is a model-derived zero crossing of cumulative GEX or an explicitly defined net-GEX function. It is a descriptive level under the selected convention, not automatically a predictive support/resistance level.

The implementation must document interpolation and whether the crossing is based on strike-ordered cumulative exposure or repriced net exposure.

## Walls
Call wall / put wall are candidate concentration levels selected by a documented ranking rule. They are not guaranteed resistance/support.

## Required validation
- dimensional/unit checks;
- independent Black-76 numerical test;
- known synthetic-chain tests;
- sign-convention invariance tests;
- missing-data tests;
- multi-expiry tests;
- sensitivity to IV source and DTE;
- sensitivity to inclusion/exclusion of far OTM strikes.

## Prohibited interpretation
Do not state “dealer is short gamma” from OI alone.
Do not state positive GEX causes price increases.
Do not state negative GEX guarantees volatility expansion.
