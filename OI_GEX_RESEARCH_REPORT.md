# OI + GEX Research Report — Initial Foundation

## 1. Research Question
Does GC options OI, ΔOI and GEX add measurable information beyond price, volume, IV and realized-volatility baselines?

## 2. Current Answer
NOT YET DETERMINED.

The repository currently has an operational prototype for OI/GEX measurement, but no completed GC out-of-sample experiment establishes incremental predictive power.

## 3. Data Sources
Primary source is CME/QuikStrike-derived GC option information. Secondary underlying-price data is currently supplied through Twelve Data. The research dataset must preserve source timestamps and publication timing.

## 4. Methodology
Use canonical contracts, historical snapshots, versioned GEX conventions and nested baselines. Separate observed data from derived calculations and inferred dealer-position hypotheses.

## 5. Mathematical Formulas
Black-76 gamma and dollar-GEX are documented in GEX_METHODOLOGY.md. Every result must identify sign convention, gamma source, multiplier and calculation version.

## 6. Assumptions
The fixed call+/put- sign convention is an explicit assumption, not an observed dealer book. Alternative conventions must be evaluated.

## 7. Data Limitations
Current QuikStrike pipeline is snapshot-oriented and may not provide publication-time metadata or sufficiently deep historical data for every research horizon.

## 8. Hypotheses
See HYPOTHESIS_REGISTRY.md. Initial hypotheses focus on volatility forecasting, pinning, gamma-flip transitions and incremental information.

## 9. Experiments
No validated experiment is currently registered as completed.

## 10. Results
No GC OOS result yet.

## 11. Out-of-Sample Results
No GC OOS result yet.

## 12. Failure Cases
Known failure modes include missing IV/Greeks, expiry mapping, stale or preliminary OI, ambiguous publication time, dealer-sign ambiguity and nearest-strike migration overinterpretation.

## 13. Robustness Tests
Required: expiry buckets, volatility regimes, event days, alternative GEX conventions, alternative Greek sources and multiple horizons.

## 14. Economic Significance
Statistical association is insufficient. Any future economic test must include transaction costs, slippage and realistic execution assumptions.

## 15. Limitations
Cross-market literature cannot be assumed to transfer to GC. Current dealer-position inference is only a proxy.

## 16. Conclusions
The project should proceed as a research-grade measurement engine first. Trading integration remains gated by OOS evidence.

## 17. Next Experiments
Build canonical GC contract/history dataset, validate GEX numerically, run baseline comparisons, then execute purged walk-forward experiments.
