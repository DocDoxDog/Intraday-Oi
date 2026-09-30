# POINT-IN-TIME MARKETSTATE CONTRACT

## Purpose

Prevent look-ahead leakage and prevent customers from seeing data that was not actually available at the decision time.

## Timestamps

Every customer-visible MarketState must carry:
- as_of
- publication_time
- availability_time
- ingestion_time

## Ordering invariants

publication_time <= availability_time <= as_of <= now + allowed_clock_skew
ingestion_time <= now + allowed_clock_skew

## Validity

Customer-visible state requires:
- VALID or OFFICIAL status;
- finite data quality in [0, 1];
- finite non-negative data age;
- configured freshness limit;
- non-empty dataset and calculation versions;
- approved source rights.

## Reject

Reject if:
- publication or availability timestamp is missing;
- availability precedes publication;
- publication/availability is after as_of;
- as_of is materially in the future;
- state is stale/incomplete/unavailable;
- rights are not approved;
- version identifiers are missing.

## Audit tuple

symbol, as_of, publication_time, availability_time, ingestion_time, dataset_version, calculation_version, rights/agreement reference, data status, data quality, source id.
