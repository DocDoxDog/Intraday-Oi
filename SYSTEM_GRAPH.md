# SYSTEM GRAPH

Status: AUDIT COMPLETE

## Current graph

    QuikStrike/CME surface
        |
        v
    UrlManager
        |
        v
    Playwright Scraper
        |
        v
    Parser
      | | | |       | | | |  +--> Twelve Data --> spot/basis + technical_context
      | | | +-----> OI Positioning
      | | +-------> OI Intelligence
      +-----------> GEX Engine
        |
        +--> Gemini Analyzer
        |
        v
    Supabase snapshots/storage
      |       |  +--> LINE
      +-----> Telegram

    MT5 --> AI Feature Engine --> Strategies --> Brain --> Final Gate --> Execution
    Research JSONL --> Evaluation --> Walk-forward

    AI-Trader GEX  - - duplicate measurement engine - -  Intraday-Oi GEX

## Actual dependency findings

1. main.py is the central orchestration point in Intraday-Oi.
2. parser.py invokes GEX enrichment.
3. main.py separately invokes OI positioning and OI intelligence.
4. gex_now.yml independently executes scraper + parser + GEX but does not become a canonical persisted calculation.
5. Ai-trader has an independent GEX calculator.
6. Ai-trader Brain currently passes zero for positioning_score and macro_score, so options positioning is not yet part of the final decision state.
7. Neither repository has a complete CME publication-time-aware canonical OI observation model.

## Target graph

    CME / entitled providers
             |
             v
    RAW IMMUTABLE DATA
             |
             v
    NORMALIZED DATA
             |
             v
    CANONICAL CONTRACT / EXPIRY MASTER
             |
             v
    POINT-IN-TIME OBSERVATIONS
       |      |       |
       v      v       v
      OI    GREEKS   FLOW
       |      |       |
       +------v-------+
           EXPOSURE
          GEX / DEX
             |
             v
        POSITIONING
             |
             v
           REGIME
             |
       +-----+-----+
       v           v
   RESEARCH     SIGNAL
       |           |
       v           v
      OOS         RISK
       +-----+-----+
             v
         AI TRADER
          /           Telegram    Vercel
             |
          Paper/Live
