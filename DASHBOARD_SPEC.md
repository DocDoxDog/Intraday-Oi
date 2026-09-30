# DASHBOARD SPEC

Status: ARCHITECTURE READY

## Product

OI POSITIONING INTELLIGENCE

Not an admin panel. Professional market-terminal information hierarchy.

## Routes

/overview
/positioning
/oi
/gex
/options
/flow
/expiration
/regime
/history
/research
/backtest
/signals
/ai-trader
/alerts
/system
/settings

## Overview

Must answer:
WHERE IS PRICE?
WHERE IS GAMMA?
WHERE IS OI?
WHAT CHANGED?
WHAT EXPIRY MATTERS?
WHAT IS THE REGIME?
HOW FRESH IS DATA?

Layout:
symbol/price/session/data age
positioning regime/gamma flip
net GEX/candidate call concentration/candidate put concentration
positioning map
OI flow/GEX flow
expiry matrix
signal/confidence/data quality

## Positioning Map

Layers:
OI
ΔOI
net GEX
absolute GEX
DEX
volume
IV

X axis = strike / price relationship.
Optional expiry filtering.

## Chain

Call | Strike | Put
Bid Ask Last Volume OI ΔOI IV Delta Gamma Theta Vega

Filters:
expiration
DTE
moneyness
strike range
spread

## Expiry Matrix

expiration
DTE
OI
OI %
ΔOI
GEX
ΔGEX
DEX
IV
IV×OI

## Research

Show:
hypothesis
dataset version
feature/model versions
train/validation/OOS
metrics
uncertainty
reproducibility

## AI trader

Show:
OBSERVE
INTERPRET
SCENARIO
RISK
ACTION
NO_TRADE_REASON

## UI rules

dark institutional
compact
semantic colors
subtle borders
high information hierarchy
no formula duplication in client code
