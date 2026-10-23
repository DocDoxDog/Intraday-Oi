# OmniRoute Evaluation Boundary

OmniRoute is evaluated as an LLM infrastructure layer only.

## Candidate placement

deterministic evidence → reasoning spine → governed gateway → OmniRoute/provider → verification → narrative

## Acceptance checks

1. Evidence references survive routing unchanged.
2. Deterministic level IDs survive routing unchanged.
3. Verification receives the same contract regardless of provider.
4. Model/provider/version are recorded for reproducibility.
5. Fallback does not silently change output semantics.
6. Timeout/failure remains fail-safe.
7. Cost and latency are measurable.
8. No execution authority is introduced.

## Non-responsibilities

OmniRoute must not calculate or decide OI, ΔOI, volume, GEX, Max Pain, Pinning, walls, gamma flip, entry/SL/TP, risk/reward or execution readiness.

Promotion requires live gateway testing plus regression tests proving evidence-reference and level-ID integrity.
