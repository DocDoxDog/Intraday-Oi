# DATA MODEL

Status: ARCHITECTURE READY

## Core

instruments
futures
options
expirations
strikes

## Raw

raw_market_data
- source
- source_file
- source_version
- fetched_at
- payload
- checksum

## Options observations

option_quotes
- option_id
- observation_time
- bid
- ask
- sizes
- last
- IV
- Greeks
- source

option_trades
- option_id
- trade_time
- price
- size
- premium
- observed side where available
- source

option_oi
- option_id
- trade_date
- observation_time
- publication_time
- availability_time
- open_interest
- volume
- data_status
- source
- dataset_version

## Derived

oi_snapshots
oi_changes
greeks
gex_snapshots
dex_snapshots
positioning_levels
regimes
features

## Research

dataset_versions
feature_versions
hypotheses
experiments
backtest_runs
backtest_results
model_versions

## Operations

signals
alerts
alert_deliveries
pipeline_runs
data_quality_events
audit_logs

## Provenance

Every derived record references dataset_version and calculation_version and retains canonical contract identity and as_of/availability time.

## PIT rule

Only records satisfying availability_time <= decision_time may enter a historical decision dataset.
