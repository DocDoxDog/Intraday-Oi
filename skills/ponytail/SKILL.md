---
name: ponytail
description: Minimal-change engineering guardrail for Intraday-Oi.
---

# Ponytail — Intraday-Oi

Use senior-engineer/YAGNI discipline.

## Before editing

1. Read the affected module and every caller.
2. Identify tests, fixtures, config and contracts touched.
3. Reuse existing helpers before adding abstractions.
4. Prefer the smallest complete change.
5. Check whether the change can alter financial facts, levels, provenance or execution gates.

## Never cut

- source/parser validation
- error handling that prevents data loss
- security
- evidence provenance
- point-in-time semantics
- calibration/holdout gates
- deterministic risk controls
- required tests

## Financial rules

- OI is positioning, not traded volume.
- ΔOI is not aggressor direction.
- GEX is context, not a directional oracle.
- A level is not a trigger.
- A trigger is not confirmation.
- LLM output cannot create or alter deterministic prices, levels, RR or risk limits.
- Missing evidence stays missing.
- Max Pain, Pinning, walls, gamma and OI are related structure, not independent votes.

## Finish

For every non-trivial change:
- run relevant tests;
- inspect the diff;
- state what was intentionally not changed;
- state unresolved risk.

Do not add wrappers, configuration knobs or future-proofing unless the task requires them.
