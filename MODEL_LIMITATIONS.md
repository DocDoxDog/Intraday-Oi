# Model Limitations

1. OI is an aggregate open-position measure. It does not identify aggressor side.
2. ΔOI identifies a change in open interest, not whether a buyer or seller initiated the trade.
3. Call/put OI does not uniquely identify dealer inventory.
4. Signed OI GEX is therefore a model assumption/proxy unless additional participant or trade-direction evidence exists.
5. Gamma depends on IV, time-to-expiry, underlying price and model assumptions.
6. Vendor Greeks and recomputed Greeks can differ because of inputs, conventions and timing.
7. Gamma flip is convention-dependent.
8. Pinning is conditional on expiry, strike distribution, liquidity, hedge mechanics and other flows; OI concentration alone is insufficient.
9. Public OI is generally lower-frequency than trade/quote data and can have publication delays.
10. Historical research must use the information set actually available at the decision timestamp.
11. GC options are options on GC futures; spot/XAUUSD is a separate instrument and must not silently substitute for the option underlying.
12. A feature can be statistically associated with future volatility without being economically causal.
13. A predictive relationship in equity index options does not automatically transfer to COMEX gold options.
14. No current repository evidence establishes live trading edge.

## Interpretation labels
OBSERVED = directly sourced.
DERIVED = deterministic mathematical transformation.
INFERRED = evidence-based but non-identified interpretation.
ASSUMED = explicit modeling choice.
