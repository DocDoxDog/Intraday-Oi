# SYSTEM INVENTORY

Status: AUDIT COMPLETE
Audit date: 2026-10-01
Scope: Intraday-Oi research/oi-gex-intelligence-foundation and Ai-trader main

## Intraday-Oi

| SYSTEM | PURPOSE | LOCATION | ENTRYPOINT | INPUT | OUTPUT | DEPENDENCIES | DATABASE | SCHEDULE | STATUS | DUPLICATES | MAIN DEBT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| URL Manager | resolve/self-heal QuikStrike session | src/url_manager.py | main.py | env, app_config, QuikStrike | session URL | Playwright, Supabase | app_config | per run | ACTIVE | none | vendor coupling, hardcoded bootstrap metadata |
| QuikStrike scraper | acquire OI/chart data | src/scraper.py | main.py | QuikStrike page | raw payload | Playwright, selectors | none | dispatch/manual | ACTIVE | gex_now duplicates path | brittle UI surface, not direct historical CME feed |
| Parser/normalizer | normalize strike rows | src/parser.py | main.py | scraper payload | normalized snapshot | parser rules, GEX | none | per run | ACTIVE | overlaps future canonical normalizer | no full PIT observation model |
| Contract model | canonical option identity helper | src/contracts.py | future consumers | contract fields | canonical contract | dataclass | none | n/a | FOUNDATION | AI data/contracts partial overlap | not wired end-to-end |
| OI positioning | OI totals/deltas | src/oi_positioning.py | main.py | current/prior OI | enriched OI | history | raw_series | per run | ACTIVE | overlaps OI intelligence | semantics split across modules |
| OI intelligence | DEX, flow hypotheses, migration | src/oi_intelligence.py | main.py | OI/ΔOI/price | exposure/events | history | oi_* | per run | PROTOTYPE | overlaps OI positioning | NEW_LONG etc. overstate evidence |
| GEX engine | GEX by strike/expiry | src/gex.py | parser | gamma, OI, IV, F, DTE | GEX/flip/walls | Black-76 | raw_series, oi_exposure_snapshots | per run | PROTOTYPE | duplicate in Ai-trader | sign assumption, selected-expiry scope |
| History | hour/today/EOD context | src/history.py | main.py | Supabase snapshots | history context | Supabase | snapshots | per run | ACTIVE | future research dataset replaces it | captured_at is not publication time |
| Twelve Data | spot/basis + OHLC | src/twelve_data.py | main.py | API | spot/CFD/OHLC | requests | snapshot | optional | ACTIVE | AI-Trader uses MT5 market feed | source mixing risk |
| Technical features | EMA/trend/sweep/BOS/FVG/Fib | src/technical_analysis.py | main.py | Twelve Data OHLC | technical_context | Twelve Data | snapshot | optional | ACTIVE | overlaps AI FeatureEngine | duplicate feature logic |
| Gemini analyzer | narrative/scenario | src/analyze.py | main.py | compact options/history | text JSON | Gemini | ai_summary | per run | ACTIVE | AI-Trader context also uses Gemini | not numeric source of truth |
| Supabase writer | persist snapshot/intelligence/media | src/supabase_client.py | main.py | all results | DB/storage | service role | several tables | per run | ACTIVE | future canonical repository | partial-write risk |
| Telegram | outbound report/plan | src/telegram.py | main.py | analysis/OI | messages/photos | Bot API | none | per run | ACTIVE | central service later | hardcoded chat ID; logic mixed with presentation |
| LINE | outbound report | src/line.py | main.py | analysis/OI | broadcast/push | LINE API | none | per run | ACTIVE | notification adapter later | trade logic mixed with presentation |
| GitHub Actions | run scrape/test/GEX | .github/workflows | workflows | secrets/repo | job results | GitHub runner | none | dispatch/push | ACTIVE | gex_now duplicates acquisition | no durable worker state |
| Screenshot/chart | render report image | src/oi_chart.py | parser/main | strike rows | PNG | matplotlib | Storage | per run | ACTIVE | future web charts overlap | presentation concern in data pipeline |

## Ai-trader

| SYSTEM | LOCATION | ROLE | STATUS | ISSUE |
|---|---|---|---|---|
| Options GEX | ai_gold/data/options/gex.py | independent GEX math | ACTIVE | duplicate source of truth |
| General contracts | ai_gold/data/contracts.py | ticks/candles/accounts/positions | ACTIVE | not an options master |
| Feature engine | ai_gold/features/engine.py | price/ATR/regime/microstructure | ACTIVE | no canonical OI/GEX features |
| Research dataset | ai_gold/research/dataset.py | decision/outcome JSONL | ACTIVE | not shared canonical market store |
| Evaluation | ai_gold/research/evaluation.py | metrics/uncertainty/gate | ACTIVE | must become PIT-aware |
| Walk-forward | ai_gold/research/walkforward.py | purged folds | FOUNDATION | no OI publication filter |
| Brain | ai_gold/brain.py | candidate + final regime | ACTIVE/FAIL-CLOSED | positioning_score=0 and macro_score=0 currently |
| Context service | ai_gold/context/service.py | macro/news/calendar/LLM | ACTIVE | incomplete event/release PIT fields |
| Decision engine | ai_gold/decision/engine.py | final decision interface | FAIL-CLOSED | currently never promotes ensemble |
| Final brain | ai_gold/final/engine.py | deterministic gate | ACTIVE | good gate skeleton |
| Execution | ai_gold/execution/service.py | MT5 execution | AVAILABLE/SHADOW | must stay downstream of gates |
| MT5 | ai_gold/mt5/client.py | broker adapter | ACTIVE | execution source, not options source |
| Monitoring | ai_gold/monitoring/* | drift/logging | ACTIVE | should also observe options pipeline |
| Dashboard | dashboard/index.html | static view | LEGACY | not target Vercel terminal |

## Cross-repository ownership conclusion

Intraday-Oi is the acquisition/reporting prototype. Ai-trader is the research/decision/execution framework. The missing shared boundary is a point-in-time canonical options dataset plus one canonical quant engine.
