# Scientific Backtest — 2026-11 — 100+100+100 Rounds

Date: 2026-11-21
Instrument: XAU/USD
Data source: Supabase project `mwqmxxipgdhbcmwoqueg`
Dataset window used here: market state 2026-10-09 → 2026-11-18; M5 bars available through 2026-11-18.

## 1. Research question

The question is not:

> Which configuration made the most money?

The question is:

> Does the proposed market mechanism survive changes in execution assumptions, sampling assumptions, costs, and time windows without being selected from the same data that evaluates it?

The answer from this study is:

**Not yet.**

There are promising mechanisms, especially Negative Gamma + H1 trend alignment, but the evidence is still too short, too regime-concentrated, and too weakly validated to call this a production trading edge.

## 2. Data quality constraints

Current rich state history is 624 `market_state_snapshots`.

Important limitations:

- The state snapshots are not uniformly spaced and should not be treated as 624 independent observations.
- A 120-minute cooldown was used for the canonical comparison to reduce serial dependence.
- The options/OI event table `oi_flow_events` is unusable for this period because its 663 rows are all `UNKNOWN` with confidence 0.
- OI Barrier Flow therefore is **not** part of this experiment.
- The current OOS period begins 2026-11-11 and ends 2026-11-18: only about eight calendar days.
- Source-level point-in-time provenance is not fully available for every historical feature field. Outcome bars are strictly after the decision timestamp, but upstream feature capture timestamps need further hardening for a full PIT claim.
- Cost/slippage is not embedded in the gross R results below; explicit cost stress is shown separately.
- Same-M5-bar stop/target collisions are resolved conservatively as stop first.
- Timeout trades use the actual last M5 close at the horizon, not a forced 0R.

## 3. Round set A — 100 exploratory combinations

The first 100-round matrix tested:

- 10 signal families
- 10 SL/TP profiles

It included Gamma Wall break, Gamma Wall acceptance, Negative Gamma, MTF alignment, IV + Negative Gamma, 3SD, and combinations.

This set is **exploratory**, not the final scientific result, because some threshold parameters were derived from the full sample (for example, GEX percentile thresholds). That is a mild sample-information leak and is not acceptable as the final promotion test.

Main lesson:

- Raw Gamma Wall Break did not remain profitable across the sample.
- Gamma Wall Acceptance produced some positive OOS configurations, but the same configurations were often negative in Train/Validation.
- Negative Gamma configurations produced strong late-OOS results, but most had very small OOS counts and weak/absent Validation coverage.
- 3SD configurations did not reproduce the earlier strong result under this state-aligned event implementation.

Round A is therefore retained as hypothesis-generating evidence only.

## 4. Round set B — corrected 100-round robustness matrix

The second experiment was pre-specified before reading the result:

### Four mechanisms

1. `GB`
   - Gamma Wall break

2. `GB_ACCEPT`
   - Gamma Wall break followed by acceptance beyond the break level

3. `NEG25_H1`
   - Net GEX <= -25M
   - H1 trend supplies direction

4. `NEG25_MTF`
   - Net GEX <= -25M
   - H1, H4 and M15 trend must agree

The -25M threshold is fixed and does not use a full-sample percentile.

### Five cooldowns

30, 60, 120, 240, 360 minutes

### Five holding horizons

30, 60, 120, 180, 240 minutes

Total:

**4 × 5 × 5 = 100 configurations**

Execution was fixed across the matrix:

- Entry: first available M5 close after state timestamp, within 10 minutes
- Stop: 1.0 H1 ATR
- Target: 1.5 H1 ATR
- Same-bar SL/TP collision: SL first
- Timeout: last M5 close at the configured horizon

### Important implementation correction

The first SQL version of Round B incorrectly cross-joined horizons before applying the cooldown `LAG()` calculation. This caused duplicated timestamps to interfere with the cooldown filter.

That run was **discarded completely**.

The corrected order is:

1. build raw signals
2. apply cooldown within family/cooldown
3. expand each accepted signal across horizons
4. execute the outcome simulation

This corrected run is the only Round B result considered valid.

## 5. Round B results

The strongest OOS gross returns came from Negative Gamma configurations.

Examples:

### NEG25_H1

Cooldown 60 / horizon 180:
- Train n=20, avg +0.229R
- Validation n=0
- OOS n=6, avg +1.020R

Cooldown 30 / horizon 180:
- Train n=75, avg +0.293R
- Validation n=0
- OOS n=44, avg +0.428R

Cooldown 30 / horizon 120:
- Train n=75, avg +0.308R
- Validation n=0
- OOS n=44, avg +0.374R

Cooldown 30 / horizon 60:
- Train n=75, avg +0.188R
- Validation n=0
- OOS n=44, avg +0.144R

This is the most important finding in the entire study:

**The Negative Gamma effect is not simply a tiny six-trade accident. Under some execution perturbations it survives and produces positive gross OOS averages with 44 OOS observations.**

But there is an even more important counterfinding:

**There is zero Validation coverage for these Negative Gamma configurations.**

So the evidence jumps from Train to late OOS without an independent middle regime.

That means the correct status is:

**PROMISING / UNVALIDATED**, not VALIDATED.

### NEG25_MTF

Cooldown 30 / horizon 240:
- Train n=56, avg +0.317R
- Validation n=0
- OOS n=40, avg +0.319R

Cooldown 30 / horizon 180:
- Train n=56, avg +0.285R
- Validation n=0
- OOS n=40, avg +0.307R

Cooldown 30 / horizon 120:
- Train n=56, avg +0.360R
- Validation n=0
- OOS n=40, avg +0.296R

Again:

The effect survives several horizons, but there is no Validation coverage.

### GB_ACCEPT

The Gamma acceptance mechanism is more interesting scientifically because it has Train + Validation + OOS observations.

For example:

Cooldown 120 / horizon 120:
- Train n=19, avg -0.005R
- Validation n=8, avg +0.185R
- OOS n=5, avg +0.414R

Cooldown 120 / horizon 180:
- Train n=19, avg +0.027R
- Validation n=8, avg +0.155R
- OOS n=5, avg +0.314R

Cooldown 120 / horizon 240:
- Train n=19, avg +0.078R
- Validation n=8, avg +0.096R
- OOS n=5, avg +0.312R

This looks more consistent than raw Gamma Break, but the sample is still only 5 OOS trades.

### GB raw break

Raw Gamma Break is much weaker.

The only configurations that were positive in all three phases with at least:
- Train >= 10
- Validation >= 5
- OOS >= 10

were:

1. cooldown 30 / horizon 240
   - Train +0.018R
   - Validation +0.438R
   - OOS +0.037R

2. cooldown 30 / horizon 180
   - Train +0.044R
   - Validation +0.407R
   - OOS +0.025R

These technically pass the sign test across all three phases, but the edge is tiny.

At a 0.10R per-trade cost load, both become negative.

So this is not a practical trading edge.

## 6. The 100-round survival test

Across all 100 corrected configurations:

- 100 total configurations
- 10 had at least 10 Train + 5 Validation + 10 OOS trades
- only 2 were positive in all three phases
- 12 were positive in Train + OOS while lacking the required Validation coverage
- all 50 Negative Gamma configurations had **zero Validation observations**

This is the key robustness result.

The apparent Negative Gamma edge is interesting but currently fails the most important scientific test:

**Can the mechanism be demonstrated in an independent middle regime before it is accepted in OOS?**

Right now, no.

## 7. Round set C — 100 block-bootstrap rounds

Canonical setup:

- cooldown = 120 minutes
- horizon = 120 minutes
- SL = 1 ATR
- TP = 1.5 ATR
- OOS only
- bootstrap unit = trading day, not individual trade
- 100 resamples with replacement

This is deliberately a block bootstrap so multiple trades on the same day are not falsely treated as completely independent.

### GB

- OOS trades: 6
- raw OOS mean: -0.583R
- block-bootstrap mean: -0.294R
- 5th percentile: -1.000R
- 95th percentile: +0.281R
- probability bootstrap mean > 0: 34%
- after 0.05R cost: -0.344R
- after 0.10R cost: -0.394R
- after 0.20R cost: -0.494R

Verdict: **reject current form**

### GB_ACCEPT

- OOS trades: 5
- raw OOS mean: +0.414R
- block-bootstrap mean: +0.700R
- 5th percentile: -0.032R
- 95th percentile: +1.235R
- probability bootstrap mean > 0: 89%
- after 0.05R cost: +0.650R
- after 0.10R cost: +0.600R
- after 0.20R cost: +0.500R

Verdict:

**Promising, but n=5 is far too small.**

This result is useful as evidence that acceptance is worth further research, not as evidence that the strategy is ready.

### NEG25_H1

- OOS trades: 6
- raw OOS mean: +0.464R
- block-bootstrap mean: +0.422R
- 5th percentile: -0.147R
- 95th percentile: +0.933R
- probability bootstrap mean > 0: 86%
- after 0.05R cost: +0.372R
- after 0.10R cost: +0.322R
- after 0.20R cost: +0.222R

Canonical six-trade OOS:
- mean ≈ +0.464R
- PF ≈ 3.54
- t-statistic ≈ 1.16
- one-sample t-test p ≈ 0.30

Verdict:

**Promising mechanism, statistically weak evidence.**

### NEG25_MTF

- OOS trades: 4
- raw OOS mean: +0.226R
- block-bootstrap mean: +0.191R
- 5th percentile: -0.447R
- 95th percentile: +0.852R
- probability bootstrap mean > 0: 58%
- after 0.05R cost: +0.141R
- after 0.10R cost: +0.091R
- after 0.20R cost: -0.009R

Verdict:

**Too small and too cost-sensitive.**

## 8. What survived the scientific attack?

### Survives

**Negative Gamma is useful as a regime/amplification filter.**

That is increasingly supported.

The data suggest that when Net GEX is deeply negative and H1 structure has a directional state, subsequent price movement can be more directional over multiple horizons.

But that does not prove:

> Negative Gamma = BUY/SELL.

The correct inference is:

> Negative Gamma increases the probability that an existing directional state can propagate.

That matches the original system thesis better than treating Gamma as a standalone directional indicator.

### Partially survives

**Gamma Wall Acceptance is more useful than raw Gamma Wall Break.**

Raw break alone is weak.

Acceptance carries more information because the market must remain beyond the barrier rather than merely touch or spike through it.

The mechanism worth keeping is:

BREAK → ACCEPTANCE → PRICE RESPONSE

not:

BREAK → ENTER

### Does not survive

**Raw Gamma Wall Break as a standalone trading rule.**

The OOS direction can reverse sharply and the gross edge is not stable enough.

### Does not survive

**3SD as a standalone “trade immediately” rule under this specific state implementation.**

Earlier 3SD tests looked much better, but this new implementation did not reproduce that performance. That means the older result was likely definition-sensitive or sample/regime-sensitive.

This is exactly the kind of contradiction we want the research system to expose.

## 9. Important scientific conclusion

The model is beginning to separate mechanisms from signals.

Current hierarchy:

1. Negative Gamma = regime / amplification context
2. Structure = directional context
3. Gamma Wall = liquidity/barrier location
4. Acceptance = state transition
5. Flow / price response = confirmation of propagation
6. Target = next structural/liquidity node
7. Risk gate = final permission

This is much stronger than a weighted indicator score.

## 10. Why the system is NOT promoted

The current evidence fails the promotion policy for obvious reasons:

- OOS trade count is nowhere near the minimum 100.
- OOS period is nowhere near 3 months.
- Validation coverage is missing for all Negative Gamma configurations.
- Several apparent winners are concentrated in the same late-November regime.
- Cost/slippage has not been fully integrated into every event.
- Source-level PIT lineage still needs stronger historical provenance.
- Multiple-trial selection is already material: 100 configurations were tested.
- The strongest-looking results are therefore exactly where PBO / multiple-testing controls matter most.

The correct status remains:

**RESEARCH / PAPER ONLY**

not LIVE.

## 11. Next experiment that should be run

The next research round should stop adding more indicators.

Instead:

### A. Build a true rolling walk-forward

Use weekly or multi-day blocks:

TRAIN → VALIDATE → EMBARGO → OOS

repeat over the full historical period.

The goal is to obtain several independent OOS regimes, not one November tail.

### B. Freeze thresholds before every OOS block

No full-sample percentile thresholds.

Examples:

- fixed GEX threshold
- train-only percentile
- train-only ATR normalization
- train-only regime thresholds

### C. Purge overlapping labels

If a trade has a 120-minute outcome horizon, embargo at least that horizon around split boundaries.

### D. Measure MFE / MAE

A lot of the current positive evidence is timeout-to-close rather than actual TP hits.

The next system should distinguish:

- TP first
- SL first
- timeout positive
- timeout negative
- MFE
- MAE

### E. Apply real execution costs

Test at least:

0R
0.05R
0.10R
0.20R
0.30R

and use actual spread/slippage/latency distributions from paper execution.

### F. Only after the above

Run:

- Wilson interval for hit rate
- bootstrap CI
- PSR
- DSR
- PBO / CSCV
- Benjamini-Hochberg correction
- walk-forward stability
- regime stability

## 12. Current knowledge status

| Hypothesis | Status | Reason |
|---|---|---|
| Negative Gamma amplifies directional movement | PROMISING | survives multiple execution horizons |
| Negative Gamma alone gives direction | REJECTED | not sufficient as standalone signal |
| Gamma Wall Break predicts continuation | WEAK | raw break unstable |
| Gamma Wall Acceptance is better than raw break | PROMISING | more consistent, but low OOS n |
| NEG25 + H1 trend | PROMISING / UNVALIDATED | strongest current candidate, no Validation |
| NEG25 + H1/H4/M15 | PROMISING / UNVALIDATED | similar, more selective |
| 3SD standalone continuation | UNSTABLE | implementation-sensitive |
| OI Barrier Flow | WAIT | historical OI event labels currently unusable |
| Basis as standalone direction | REJECTED | contextual only |
| IV as volatility urgency filter | PROMISING | not yet proven for PnL |

## 13. Golden Rule

Do not promote a strategy because one OOS column is green.

Promote only when:

- the mechanism is explainable,
- the event definition is frozen,
- the threshold is frozen,
- the data are point-in-time valid,
- multiple walk-forward OOS blocks agree,
- cost-adjusted expectancy stays positive,
- multiple-testing controls pass,
- paper execution survives,
- and the result continues to survive new unseen data.

Current conclusion:

**The OS has promising research signals, but it does not yet have a scientifically proven profitable trading strategy.**
