# OI / GEX Research Review

Date: 2026-10-01
Scope: GC first, with transferable options-market evidence clearly labeled.

## Primary-source findings

### CME
CME defines open interest as contracts that remain open, counting one side for OI calculation, while Change is the day-over-day change in OI. This confirms that OI and OI change are distinct measurements. citeturn0search0turn0search1
CME's Daily Volume and Open Interest report is preliminary at end of day and official data is released the following morning; preliminary and final values can differ. This creates a publication-time constraint for backtests. citeturn0search5turn0search17
CME's Open Interest Profile explicitly supports OI and OI-change views by expiration and strike. citeturn0search3turn0search16
CME's Open Interest Heatmap supports strike/expiration concentration and one-day, one-week and one-month OI changes. citeturn0search15
GC is a 100-troy-ounce futures contract; GC options are options on the futures and have their own expiration/settlement specifications. The canonical contract master therefore cannot treat XAU/USD spot as the option underlying. citeturn0search137turn0search18

### Cboe
Cboe explains gamma hedging as the change in option delta and notes that long-gamma market-maker hedging can oppose underlying moves while short-gamma hedging can reinforce them. This describes a conditional hedge mechanism; it does not establish that public OI reveals dealer sign. citeturn0search12
Cboe's research catalog includes recent work specifically testing the impact of 0DTE index options on volatility, reinforcing the need to separate expiry buckets rather than pool all options. citeturn0search9

## Academic / research evidence

1. Soebhag (2023), Journal of Empirical Finance, reports that net gamma exposure is related to future equity returns and volatility, with evidence consistent with hedge rebalancing as a mechanism. This is equity evidence, not proof for GC. citeturn0search2
2. Muravyev and Ni (2012), Journal of Financial Economics, find expiration-day pinning in S&P 500 futures and relate it to option-market hedging dynamics; they also examine OI and volume as explanatory variables. This supports testing pinning, not treating OI concentration as guaranteed support/resistance. citeturn1search1
3. Branger and Schlag (2008/2009), JFQA, show that discrete trading and model misspecification can make hedging-error based volatility-premium tests unreliable. This supports explicit model-risk controls for Greek-derived features. citeturn1search2
4. Hu and Jacobs (2019), JFQA, document relationships between underlying volatility and expected option returns. This supports IV/RV as essential baselines rather than treating options features in isolation. citeturn1search3
5. A 2026 SSRN methodology by Jangir explicitly identifies the fixed call+/put- GEX convention as an assumption and proposes using order-flow, ΔOI and ΔIV to relax it. It is a recent methodology paper, not established evidence, so it belongs in mixed/experimental evidence. citeturn1search4
6. Ardia and Vaudescal (2026) report that a public-OI-rebuilt gamma-variance relation remains observable in their SPX study, with differences between non-0DTE and 0DTE. This is highly relevant to the planned bucketed validation, but it is not GC evidence. citeturn1search5
7. Sen (2026) documents a fully disclosed GEX engine for CME S&P 500 and COMEX gold futures options using Black-76 and a standard dealer-sign convention. It is useful for methodology comparison, but its existence does not validate the convention empirically. citeturn1search6
8. Sahu (2026) argues that aggregate dealer gamma inferred from public OI is only partially identified and that the sign can remain undetermined under plausible participant-book balances. This is directly contrary to treating signed OI-GEX as observed dealer inventory. It is an SSRN working paper, not yet peer-reviewed evidence. citeturn1search7
9. NBER research using call/put OI as a control variable demonstrates that OI is used empirically, but also places it alongside other variables such as volatility and option volume. OI should therefore be evaluated as an incremental feature rather than presumed sufficient. citeturn1search8
10. NBER work on option information and volume documents an informational role for option trading in some models/empirical settings. This motivates adding volume/quote/order-flow variables when available instead of attempting to infer trade direction from OI alone. citeturn1search9
11. Chopra (2026) proposes a framework combining OI, IV, Greeks, intraday prices, volume and liquidity, and explicitly notes that OI alone cannot establish dealer gamma direction. It is a recent working paper and should be treated as methodological evidence. citeturn1search0

## Evidence classification

### Supporting / motivating evidence
- OI concentration and OI change are legitimate measurable state variables. CME directly exposes them by strike and expiry. citeturn0search3turn0search15
- Gamma/hedging mechanisms have documented relationships with volatility and expiration behavior in equity/index markets. citeturn0search2turn1search1turn1search5

### Contradicting / cautionary evidence
- Public OI does not uniquely identify dealer inventory sign. citeturn1search7turn1search0
- Fixed call+/put- sign is an assumption, not an observed fact. citeturn1search4turn1search7

### Mixed evidence
- Pinning and gamma/volatility effects are documented but depend on expiry, liquidity, market structure and other flows. citeturn1search1turn1search0
- Public-OI gamma can contain predictive information in some markets, but transfer to GC remains untested. citeturn1search5turn0search2

### Untested for this project
- Incremental GC predictive value of OI over price/volume/IV/RV.
- GC public-OI GEX versus alternative sign conventions.
- GC gamma-flip predictive value.
- GC OI concentration and pinning.
- GC negative/positive GEX versus future realized volatility.
- ΔOI plus quote/order-flow evidence versus OI-only inference.

## Research conclusion
The evidence justifies building a measurement and validation engine. It does not justify treating current signed GEX as observed dealer positioning or using it as a trading signal before out-of-sample GC validation.
