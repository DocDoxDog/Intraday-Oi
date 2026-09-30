# DATA LICENSING

Status: LEGAL_REVIEW_REQUIRED

## Product data classes

RAW DATA
Direct source observations, screenshots, feed payloads, raw article content.

DERIVED DATA
GEX, DEX, normalized OI structures, transformations and calculations.

ANALYTICS
MarketState, confirmation metrics, clustering, scenario states and analysis metadata.

DISPLAY
Values/charts rendered to customers.

API
Machine-readable customer delivery.

ALERT
Telegram/customer notifications.

REDISTRIBUTION
Anything allowing a customer or downstream system to obtain source-like data.

## Default commercial boundary

RAW DATA:
Do not expose to customers unless license explicitly permits it.

DERIVED DATA:
License review required because exchange/vendor agreements may define derived works and distribution.

ANALYTICS:
May be commercially useful, but licensing restrictions can still apply when analytics are derived from licensed market data.

DISPLAY/API/ALERT:
Treat as distribution. Require documented rights.

## CME

CME explicitly offers market-data licenses for internal display, internal non-display,
distribution, and derived data products. Its derived-data program includes products
such as reference values, risk-management services and CFDs. Therefore a commercial
product built from CME futures/options data should be designed as a licensed use case,
not assumed to be unrestricted.

## FRED / government data

FRED's API terms require attribution and note that some series are third-party owned.
EIA's API terms explicitly allow service development using EIA data with attribution
and prohibit implying EIA endorsement. ECB public statistics have a reuse policy
allowing free reuse with source citation and without modifying statistics/metadata,
subject to exclusions.

## News

Reuters, Bloomberg, AP, FT, WSJ and similar premium sources are treated as
LICENSE_REQUIRED until an executed agreement proves the intended use.

## QuikStrike

Current QuikStrike acquisition remains a prototype/legacy source path.
No commercial redistribution rights are assumed from public access.

## Evidence ledger

Every source configuration should record:

source_name
access_method
agreement_reference
rights_scope
commercial_use
redistribution
attribution
retention_period
effective_from
effective_to
review_owner
review_status
