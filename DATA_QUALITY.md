# Data Quality Specification

## Hard failures
- Missing symbol/expiry/strike/type.
- Invalid expiry ordering.
- Negative OI or volume.
- Duplicate canonical contract observations at the same timestamp without a deterministic dedupe rule.
- Timestamp timezone ambiguity.
- Publication time after feature timestamp.
- Contract mapping conflict.
- Missing underlying price when GEX is requested.

## Soft warnings
- Missing IV/Greeks.
- Sparse strike coverage.
- Stale quotes.
- Wide bid/ask.
- Preliminary OI used where official OI is unavailable.
- Derived rather than source-provided Greeks.

## Quality dimensions
1. completeness
2. uniqueness
3. temporal integrity
4. contract integrity
5. numerical validity
6. source provenance
7. publication-time availability
8. strike/expiry coverage

No imputation of OI, volume, or dealer position is permitted.
