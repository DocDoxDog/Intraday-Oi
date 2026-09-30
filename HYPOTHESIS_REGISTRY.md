# Hypothesis Registry

| ID | Hypothesis | Primary outcome | Baseline | Status |
|---|---|---|---|---|
| H001 | Larger signed net GEX is associated with lower future realized volatility | RV / variance | price+ATR+IV+RV | UNTESTED |
| H002 | More negative signed net GEX is associated with higher future realized volatility | RV / range | same | UNTESTED |
| H003 | Price proximity to large OI concentration is associated with expiry-day pinning | distance-to-strike | expiry/calendar baseline | UNTESTED |
| H004 | Gamma-flip crossings are associated with volatility-regime transitions | regime transition | price/RV change point | UNTESTED |
| H005 | Large ATM ΔOI is associated with future activity/range | future range | price+volume+ATR | UNTESTED |
| H006 | OI+GEX improves volatility forecasting beyond price/volume/IV/RV | forecast error | nested baselines | UNTESTED |
| H007 | OI concentration adds information about future range after controlling for realized volatility | future range | RV baseline | UNTESTED |
| H008 | GEX effects differ materially by DTE bucket | interaction effect | pooled baseline | UNTESTED |
| H009 | 0DTE/near-expiry effects differ from weekly/monthly effects | interaction effect | expiry bucket | UNTESTED |
| H010 | ΔOI plus quote/trade-direction evidence improves positioning inference versus OI alone | inference quality | OI-only | UNTESTED |

For every experiment record: dataset version, feature version, model version, sample window, leakage controls, result, confidence interval and failure cases.
