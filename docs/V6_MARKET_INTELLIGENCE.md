# V6 Market Intelligence

V6 completes the deterministic-to-reasoning architecture without turning the LLM into a trading oracle.

Architecture:
Raw Market Data -> Canonical State -> Evidence Ledger -> Relationship/Conflict -> Conditional Scenario -> Regime Fingerprint -> Point-in-Time Episodic Retrieval -> Research Gate -> LLM Narrative -> Verification -> Existing Execution Gate

## Regime fingerprint
Production records trend, volatility, gamma, auction, liquidity, flow, narrative, event and location state. A stable hash identifies the state without creating a directional score.

## Episodic memory
Historical episodes are eligible only when information_time <= decision_asof. Production retrieval exposes similarity and evidence context, but never injects future outcome labels into current evidence.

## Research gate
Candidates must pass measurement, chronological association, purged+embargoed splits, untouched OOS, transaction costs, calibration/stability and governed promotion. A research pass never automatically enables production.

## Evidence semantics
TPO/auction = location and acceptance. 3sigma = distribution extremeness. Blocks = local size anomaly, not direction. Flow = aggression/impact confirmation. OI = positioning. GEX = dealer-gamma context. Smile/skew/term structure = volatility/tail context. Narrative/social/web = external context subject to timestamp and authorization gates.

## Safety
External adapters use public or authorized data, respect provider terms/rate limits, and preserve timestamps. No credential guessing, access bypass, or private-account extraction is part of V6.

## Definition of done
Runtime emits the V6 bundle, CI covers governance invariants, dashboard displays it, and the PR remains unmerged until CI/replay/OOS evidence is green.
