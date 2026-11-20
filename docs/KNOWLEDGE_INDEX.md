# Knowledge System Index

Intraday-OI stores knowledge in three layers.

## 1. Canonical domain knowledge

- skills/gold-market-intelligence/KNOWLEDGE.md
  - options Greeks
  - Gamma/GEX semantics
  - DEX/Vanna/Charm
  - market makers
  - fund positioning
  - macro
  - microstructure
  - technical structure
  - econophysics
  - seasonality
  - structural path
  - event semantics
  - research discipline

## 2. System-level knowledge

- docs/KNOWLEDGE_BASE.md
  - full market-intelligence operating model
  - Gamma Wall state machine
  - OI interpretation
  - IV/skew/DTE
  - basis/term structure
  - 3SD regime
  - flow -> price response
  - liquidity
  - market physics
  - scenario engine
  - risk/execution
  - AI Trader
  - MCP
  - canonical state
  - memory architecture

- docs/KNOWLEDGE_GRAPH.md
  - node types
  - relationships
  - mechanism graph
  - scenario graph
  - evidence lifecycle

## 3. Empirical knowledge

- docs/RESEARCH_FINDINGS.md
  - internal event studies
  - preliminary OOS observations
  - sample sizes
  - cost stress
  - known limitations
  - next validation targets

## Epistemic rule

Every knowledge item must be labeled with evidence semantics where possible:

FACT
DERIVED
MODEL_ASSUMPTION
CONSISTENT_WITH
HYPOTHESIS
UNKNOWN
DEGRADED
WAIT
NO_TRADE

## Versioning rule

Do not silently overwrite historical knowledge.

When a rule changes:
1. create a new version
2. record why it changed
3. preserve old evidence
4. link the new rule to the old rule
5. re-run affected research
6. record whether the old hypothesis was validated, rejected or deprecated

## AI usage

The AI should retrieve knowledge before reasoning about a specialized situation.

Knowledge is not a prompt dump. It is structured domain memory that should be connected to:
market state -> mechanism -> scenario -> decision -> outcome -> research update.

## Important distinction

Knowledge is not proof.

A rule in this repository can be:
- conceptual
- derived
- hypothesis
- promising
- validated
- rejected

The AI must not upgrade a hypothesis to a fact merely because it sounds plausible.
