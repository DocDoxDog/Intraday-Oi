# Financial Engineering Upgrade — November 2026

This upgrade selectively integrates the financial-engineering components from
the October upgrade archive into the current main architecture. It does not
replace newer OI ingestion, multi-domain reasoning, OHLC candidate generation,
microeconomics, or Telegram Top-5 ranking work.

## Added analytics

- **Spot-grid Gamma Flip:** Reprices per-strike Black-76 gamma across a
  hypothetical forward-price grid. Reports the zero-gamma crossing under
  explicitly named dealer-sign assumptions and preserves the legacy
  cumulative-strike crossing as a fallback.
- **Dealer-sign scenarios:** equity_convention, dealer_short_calls, and
  dealer_short_both make the assumed call/put inventory signs explicit.
  OI does not identify which side owns the option; scenario agreement is not
  proof of actual dealer positioning.
- **ATM IV and 25-delta skew:** Interpolates per-strike IV at the futures
  forward when the chain brackets it. Computes 25-delta put-minus-call skew
  only when source deltas support interpolation. Whole-chain mean IV remains
  separately identified.
- **OHLC realized volatility:** Computes close-to-close and Parkinson
  estimators from stored M5/M15/H1 bars, filters returns spanning maintenance
  or weekend gaps, and returns UNKNOWN when coverage is insufficient.
- **Horizon sigma and stop-noise diagnostics:** Estimates one-sigma price
  distance over 1h/4h/1d trading horizons and a driftless barrier-touch
  diagnostic. These are descriptive risk measures, not directional forecasts
  or probabilities of a trade winning.

## Safety and compatibility

- Existing deterministic Entry/SL/TP geometry and the Top-5 candidate limit
  remain authoritative.
- evaluate_setup_risk retains its prior PASS/NO_TRADE decision semantics.
  Stop-noise warnings and recommended risk scale are advisory and do not
  rewrite the route or position size.
- Missing IV, delta, OHLC, OI, or DTE remains unavailable/UNKNOWN.
- No new Supabase schema migration is required for these JSON evidence fields.
- The upgrade archive's separate commercial Phase 5 migrations and its
  different Supabase project reference are intentionally excluded.
