# DUPLICATE SYSTEMS

Status: AUDIT COMPLETE

| SYSTEM | ACTION | TARGET | REASON |
|---|---|---|---|
| GEX engine A/B | MERGE | one canonical options quant package | two independent formulas |
| OI positioning modules | MERGE | canonical OI engine | overlapping responsibilities |
| Flow labels | REPLACE SEMANTICS | canonical flow hypothesis engine | current labels overclaim |
| Options contract identity | MERGE | canonical options master | avoid inconsistent mappings |
| Research JSONL + DB | MERGE RESPONSIBILITY | DB canonical, JSONL export/fixture | shared PIT research needs relational joins |
| Technical feature logic | SELECTIVE MERGE | one feature layer | ATR/trend style logic overlaps |
| Telegram reporting + future command layer | CENTRALIZE | services/telegram | separate transport from business logic |
| GEX workflow + normal scrape | MERGE | one pipeline worker | duplicate acquisition/calculation |
| Scheduler ownership | CENTRALIZE | worker-control | avoid overlapping runs |
| Price sources | KEEP WITH EXPLICIT PURPOSE | source registry | MT5 execution price differs from options futures reference |

No REMOVE action is authorized yet. All removals follow:
ADAPTER -> DUAL RUN -> COMPARE -> CUTOVER -> OBSERVE -> REMOVE.
