# COMPETITOR RESEARCH

Status: RESEARCH COMPLETE
Date: 2026-10-01

## CME / QuikStrike

CME provides OI and OI change by strike, put/call and expiration, comparison windows, column/matrix heatmaps, OI profiles, most-active-strike views, weekly reports and COT-related views. These are useful reference patterns for the platform's information architecture. 
Sources:
https://www.cmegroup.com/tools-information/quikstrike/open-interest-heatmap.html
https://www.cmegroup.com/tools-information/quikstrike/quikstrike-user-guides-open-interest.html
https://www.cmegroup.com/tools-information/quikstrike/volume-open-interest-tools.html

## SpotGamma

TRACE combines real-time modeled GEX, OI and Net OI by strike and offers participant and 0DTE views. Useful concept: multiple positioning layers on one strike axis.
Source:
https://support.spotgamma.com/hc/en-us/articles/33608227551379-What-is-the-Strike-Plot-in-TRACE

## MenthorQ

The Options area is organized as Matrix, Heatmap and Exposure. Its documented metrics include Net GEX, Net DEX, Absolute GEX/DEX, OI, Volume and IV multiplied by OI. Useful concept: term-structure summary -> drilldown -> strike detail.
Source:
https://menthorq.com/guide/options-menu/

## Unusual Whales

Options Flow emphasizes filters, configurable columns, sorting, saved trades, charts and live flow. Exchange-provided trade detail includes contract, bid/ask, spot, size, premium, OI, volume and flags.
Sources:
https://docs.unusualwhales.com/features/2-options-flow/
https://docs.unusualwhales.com/features/flow-status-indicator-live-options-feed/

## TradingView

Options Chain supports multi-expiration view, calls/puts/straddle views, bid/ask/spread, IV, Greeks, volume and strike/expiration filters. TradingView also documents daily OI availability for traditional futures, reinforcing our EOD vs intraday separation.
Sources:
https://www.tradingview.com/support/solutions/43000760837-options-chain-overview/
https://www.tradingview.com/support/solutions/43000685269-open-interest/

## Koyfin

Koyfin focuses on custom views, watchlists and saved dashboards. Useful concept: persistent operator workspace after the data model is stable.
Sources:
https://www.koyfin.com/features/
https://www.koyfin.com/features/custom-dashboards/

## Research / academic evidence

Jangir 2026: fixed call/put GEX sign is an assumption; a participation-calibrated approach adds order flow, ΔOI and ΔIV. Validation is left to empirical work.
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7295618

Ardia & Vaudescal 2026: public-OI reconstructed non-0DTE gamma is associated with next-bar realized variance in SPX; this is not evidence for GC until separately tested.
https://papers.ssrn.com/sol3/Delivery.cfm/7202999.pdf?abstractid=7202999&mirid=1&type=2

Dim, Eraker & Vilkov: relationships between market-maker inventory gamma, intraday volatility and reversal behavior in 0DTE SPX options; cross-asset hypothesis source, not GC validation.
https://papers.ssrn.com/sol3/Delivery.cfm/4692190.pdf?abstractid=4692190

Sahu 2026: public OI can only partially identify dealer gamma; its sign can remain undetermined.
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7398538

Chopra 2026: expiration behavior depends jointly on dealer positioning, OI concentration, price/strike location, IV, liquidity, order flow and new information; OI alone does not reveal dealer side.
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7222220

Weiss et al. 2026: Bitcoin expiration effects vary with ATM OI and gamma exposure. Cross-asset only.
https://www.sciencedirect.com/science/article/pii/S1544612326008688

## Synthesis

INDUSTRY DOES:
visualize OI/GEX/exposure by strike and expiry; scan flow; save views; alert.

ACADEMIA SUPPORTS:
testing gamma/OI/flow/expiry relationships with controls.

CONTROVERSIAL:
dealer sign, gamma flip, causal interpretation of walls/pinning.

OBSERVED:
exchange OI, quotes/trades, IV/Greeks where sourced.

INFERRED:
dealer positioning, flow intent and hedging regime.

OUR DIFFERENTIATION:
provenance + PIT history + reproducibility + model transparency + AI integration + Telegram operations.
