# Data Dictionary — OI/GEX Research

## Raw option observation
| Field | Meaning | Required | Provenance |
|---|---|---:|---|
| symbol | canonical underlying | yes | source/contract master |
| root | option root | yes | exchange/source |
| exchange | venue | yes | source |
| underlying | underlying futures contract | yes | contract master/source |
| option_type | CALL/PUT | yes | source |
| expiration | expiration timestamp/date | yes | source |
| strike | strike price | yes | source |
| timestamp | observation time | yes | ingestion |
| publication_time | when data became knowable | research-critical | source/metadata |
| bid | option bid | nullable | source |
| ask | option ask | nullable | source |
| bid_size | bid size | nullable | source |
| ask_size | ask size | nullable | source |
| last | last price | nullable | source |
| volume | traded volume | nullable | source |
| open_interest | end-of-period/open interest | nullable | source |
| oi_change | source-reported OI change | nullable | source |
| implied_volatility | IV | nullable | source/derived |
| delta | delta | nullable | source/derived |
| gamma | gamma | nullable | source/derived |
| theta | theta | nullable | source/derived |
| vega | vega | nullable | source/derived |
| underlying_price | futures price | yes for GEX | source |

## Derived fields
- dte: time from observation to expiry using explicit timezone convention.
- oi_zscore: standardized OI against a trailing research window.
- doi_zscore: standardized OI change.
- dollar_gamma: OI × gamma × multiplier × F² × 0.01.
- net_gex: signed aggregation under a named convention.
- gamma_flip: documented zero-crossing level.
- distance_to_gamma_flip: spot/futures distance in price or normalized units.
- data_quality: reproducible quality score from completeness/timestamp integrity, not a subjective confidence score.

## State semantics
Every field must carry enough metadata to distinguish OBSERVED, DERIVED, INFERRED, ASSUMED where applicable.
