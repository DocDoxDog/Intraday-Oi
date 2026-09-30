# MIGRATION PLAN

Status: ARCHITECTURE READY

1. BASELINE
Capture current GEX/OI/DEX/levels/message outputs and versions.

2. CANONICAL DATA ADAPTER
Add instrument/future/option/expiry/strike master, raw payloads, publication/availability times and checksums.

3. QUANT ADAPTER
Wrap existing GEX behind canonical interface.

4. PARITY
Run old and canonical GEX on identical observations. Record row-level deltas and reasons.

5. DUAL RUN
Keep legacy + new calculation concurrently until material differences are explained.

6. RESEARCH
Move AI-Trader research onto canonical PIT datasets. JSONL remains export/fixture.

7. TELEGRAM
Extract command/alert service. Keep existing formatter as adapter until parity.

8. VERCEL
Build read models/API over canonical data. No client-side heavy calculations.

9. AI
Inject structured OI/GEX/IV/expiry state into AI-Trader. Preserve fail-closed gate.

10. PAPER
Run signals without live execution.

11. CANARY
GC only, then expand.

12. CLEANUP
Remove duplicate GEX, duplicate scheduler and obsolete trade logic only after observation.
