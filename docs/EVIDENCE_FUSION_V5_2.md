# Evidence Fusion V5.2

The system is upgraded from indicator aggregation to an evidence graph:

feature -> evidence -> relationship -> conflict -> scenario -> execution gate

## OOP

- Evidence: immutable value object with provenance.
- Relationship: typed relation among evidence nodes.
- Conflict: explicit contradiction with resolution hint.
- EvidenceLedger: deterministic evidence collection.
- EvidenceFusionEngine: application service that composes the graph.

## Research-derived principles

FinMem motivates layered memory rather than stuffing all history into one prompt.
TIEM motivates timestamp-gated evidence and provenance-aware retrieval.
FinMultiTime motivates modality-specific ingestion with a separate fusion layer.
Order-flow research motivates separating aggression, blocks, displacement and absorption.
IV-surface research motivates keeping skew/smile/term structure as risk-context features.
Auction-market research motivates treating POC/VAH/VAL/TPO as acceptance/location state.
Leakage-aware LLM benchmarks motivate point-in-time replay, audit trails and cost-aware OOS validation.

## Production boundary

This engine:
- never creates a BUY/SELL score;
- never fabricates missing values;
- never gives LLM execution authority;
- keeps triggers/invalidation source-derived.

External adapters may publish:
raw_series.social_intelligence
raw_series.youtube_intelligence
raw_series.tiktok_intelligence
raw_series.facebook_intelligence
raw_series.web_intelligence
raw_series.narrative_intelligence

External items should contain timestamp, source id, entity/asset, extraction version, claim, direction and confidence. Untimestamped data must not enter point-in-time research.

## Research gate

A feature only becomes execution-relevant after:
1. point-in-time replay;
2. missing-modality testing;
3. regime split;
4. out-of-sample evaluation;
5. transaction-cost sensitivity;
6. search/selection audit;
7. calibration and reliability analysis.
