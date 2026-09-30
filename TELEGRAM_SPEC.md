# TELEGRAM SPEC

Status: ARCHITECTURE READY

Telegram is the operations/control plane, not a second quant engine.

## Commands

/start
/help
/status
/gc
/oi
/gex
/flow
/regime
/levels
/expiry
/alerts
/report
/backtest
/ai

## /gc

Return:
price
session
positioning regime
gamma flip
candidate call/put GEX concentrations
net GEX
data age
confidence
data quality

Buttons:
GEX | OI | EXPIRY | LEVELS | CHART

Buttons query canonical services only.

## Security

Required:
authorized user ID
authorized chat ID
role
rate limit
audit log
callback verification

Roles:
VIEWER
RESEARCH
OPERATOR
ADMIN

Trading commands disabled by default.

## Alerts

Types:
GAMMA_FLIP_CROSS
GEX_REGIME_CHANGE
LARGE_OI_CHANGE
LARGE_GEX_CHANGE
OI_CONCENTRATION
VOLATILITY_EXPANSION
VOLATILITY_COMPRESSION
EXPIRY_RISK
DATA_STALE
DATA_FAILURE
PIPELINE_FAILURE
AI_SIGNAL
TRADE_EXECUTION
RISK_EVENT

Each event:
dedup_key, severity, event_time, as_of, evidence, cooldown, last_sent, acknowledged.

## Trading safety

TRADE -> SIGNAL -> RISK -> CONFIRMATION -> EXECUTION
with kill switch.

Current audit: outbound messaging exists, but authenticated inbound control/RBAC/cooldown/ack and separation from trade-plan logic are not yet present in the inspected OI module.
