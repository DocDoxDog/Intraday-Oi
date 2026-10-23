# Engineering Intelligence Stack

## Status

Research/integration boundary for Intraday-Oi. This records the REA decision before production merge.

## Canonical roles

| Tool | Role | Boundary |
|---|---|---|
| Graphify | Codebase knowledge graph / architecture tracing | Development-time only |
| Ponytail | Minimal-change/YAGNI engineering guardrail | Agent behavior / review |
| OmniRoute | LLM gateway and model routing | Downstream LLM boundary only |

These tools are not part of the financial decision engine.

## REA findings

### Graphify

Use Graphify first to trace the real repository architecture, dependencies and data flow. It can structurally extract code relationships and expose query/path/explain operations. Extracted and inferred relationships must remain distinguishable.

Questions to answer:
- What calls scraper, parser and analysis?
- Where are OI, GEX, levels and flow derived?
- Which branch contains each subsystem?
- Where can LLM output alter deterministic values?
- Which modules duplicate decision logic?
- What is the actual path into Telegram, dashboard and Supabase?

Graphify output is engineering evidence, not financial evidence.

### Ponytail

Use Ponytail before coding, refactoring, dependency selection and branch reconciliation. It enforces smallest-complete-change discipline while preserving validation, tests, security and financial-data safeguards.

### OmniRoute

OmniRoute is infrastructure only. Candidate placement is downstream of deterministic evidence and reasoning:

SOURCE → DETERMINISTIC ENGINE → EVIDENCE LEDGER → REASONING → GOVERNED LLM GATEWAY/OMNIROUTE → VERIFICATION → NARRATIVE

It must never generate or override OI/GEX/Max Pain/Pinning, levels, RR, risk gates or execution readiness.

## Branch REA

Comparison against main found:

- v5-reasoning-intelligence-dashboard: +18 commits
- v5-2-evidence-fusion-research: +27 commits
- v6-market-intelligence: +57 commits
- v6-human-narrative: +65 commits
- release/flow-intelligence-v1: diverged, +6 commits
- research/oi-gex-intelligence-foundation: diverged, +220 commits

Decision:
- v6-market-intelligence is the research baseline for this stack.
- release/flow-intelligence-v1 is a separate flow/decision line and must be reconciled deliberately.
- research/oi-gex-intelligence-foundation is too divergent to merge wholesale; use only audited components.
- v6-human-narrative stays downstream of deterministic reasoning and verification.

## Target architecture

SOURCE
→ RAW
→ NORMALIZE
→ DETERMINISTIC OI/GEX/OPTIONS
→ EVIDENCE LEDGER
→ REASONING / DECISION SPINE
→ FLOW / INTENT RELATIONSHIPS
→ GOVERNED LLM GATEWAY
→ LLM VERIFICATION
→ CUSTOMER NARRATIVE
→ SUPABASE / TELEGRAM / DASHBOARD

Deterministic layers own numbers and levels. Reasoning owns relationships and conflicts. LLM owns explanation, not financial facts.

## Options-intelligence rule

OI, GEX, Max Pain, Pinning, walls, gamma flip, IV/skew and related positioning constructs are one connected positioning structure, not independent votes.

Preserve source provenance, observation time, information time, calculation method, uncertainty and conflicts. No single metric is a directional oracle.

## Live-test gate

Before calendar/outcome logging or feature expansion, run the live workflow and inspect:
1. intent flow: status=...
2. llm_verification
3. ERROR / Traceback / Exception / FAILED
4. mobile แผนตาม Flow rendering

If intent flow is INSUFFICIENT, repair the adapter/connector from actual missing fields.

## Adoption

- Graphify: external development tooling.
- Ponytail: repository skill/agent policy.
- OmniRoute: evaluated downstream gateway; not promoted from architecture review alone.

## Non-goals

No new trading strategy, no fabricated data, no participant identity claims, no execution authority, and no replacement of live validation with static architecture claims.
