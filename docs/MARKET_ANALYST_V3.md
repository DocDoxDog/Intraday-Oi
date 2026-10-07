# Market Analyst V3

V3 changes the analyst contract from prose-first to evidence-first reasoning.

Pipeline:
RAW SOURCES -> CANONICAL STATE -> EVIDENCE -> REGIME -> CONFLICT -> SCENARIO -> RISK/PLAN -> NARRATIVE -> VERIFIER

Invariants:
- deterministic calculations remain the source of market truth;
- LLM cannot create unsupported numeric facts;
- OI/GEX are evidence, not directional truth;
- dealer positioning is never asserted without direct evidence;
- conflicting evidence produces conditional scenarios rather than forced BUY/SELL;
- missing data is UNKNOWN, never silently zero or guessed;
- trade plans are conditional and do not grant execution authority;
- narrative is presentation, not computation.

V3 is intentionally additive. Existing V2 delivery remains available while callers migrate.
