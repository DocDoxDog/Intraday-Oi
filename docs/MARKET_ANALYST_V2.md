# Market Analyst V2

## Evidence-first pipeline

RAW EVIDENCE -> CANONICAL MARKET STATE -> ANALYST -> SETUP/RISK -> DELIVERY

CME's QuikStrike documentation explicitly describes expiration-level OI and a heatmap across strike and expiry. The implementation therefore treats real expiration identity as first-class data rather than collapsing everything into one DTE.

## Phase 1 delivered

- Scrape multiple Gold expirations in one browser session.
- Preserve expiration code and actual DTE.
- Persist normalized expiration and strike observations.
- Build deterministic multi-expiry Gamma Matrix.
- Render a Telegram-ready Gamma Table image.
- Send Gamma Table before the original QuikStrike OI screenshot.
- Expose the multi-expiry structure to the governed LLM context.
- Keep missing matrix cells as NULL/UNKNOWN rather than zero.
- Keep WAIT separate from AI provider failure.
- Do not create entry/SL/TP until a deterministic setup and risk layer exists.

## Telegram delivery contract

Phase 1 sends:

1. Gamma Table image
2. QuikStrike OI source screenshot
3. Main analyst narrative

Phase 2 will add:

4. Conditional trade plan from setup + risk gates

The Telegram renderer is presentation only. It does not derive a trade plan.

## Canonical option identity

The primary key for term structure is:

product + expiration_code + observation_time

DTE is an attribute of that observation, not the identity itself.

## Data quality

- Missing strike/expiration observation stays NULL.
- OI is not treated as traded intraday volume.
- OI delta is UNKNOWN when no valid baseline exists.
- Gemini cannot invent numerical market levels.
- AI unavailable is not the same state as WAIT.

## Cross-repo ownership

- quikstrike-hourly-bot: raw QuikStrike acquisition
- News-bot: news evidence acquisition
- Intraday-Oi: canonical options/OI/GEX and multi-expiry state
- supaBOT: market intelligence orchestration
- Ai-trader: setup/risk/execution
- QontWise-TELEGRAM: technical evidence provider
- CPH-Dashboard: MT5 portfolio operations
- Integrated-Trading-Bot: legacy/migration reference
