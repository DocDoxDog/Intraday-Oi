# Gold Market Intelligence Dashboard

Mobile-first dashboard for the Intraday-Oi market intelligence pipeline.

## UI order

1. Current Futures / Spot / Basis
2. Market Regime
3. Action Zones
4. Multi-expiration Gamma Table
5. Key Levels
6. Trade Plan
7. Technical / Flow read
8. Macro context

## Data boundary

The dashboard reads the latest `options_flow_snapshots` row through a server-side API route.

- Supabase service-role credentials never reach the browser.
- Gamma cells come from persisted QuikStrike-derived `raw_series.multi_expiry_gamma`.
- Trade plans come from the persisted deterministic/verified analyst output.
- Missing source values remain `—`.
- The UI does not calculate GEX, OI, RR, SL or TP.

This follows the repository's evidence-first standard: deterministic market math remains the source of truth; AI is an interpretation layer.

## Local development

```bash
cd dashboard
cp .env.example .env.local
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Vercel

Create a Vercel project from this repository and set **Root Directory** to `dashboard`.

Required server-side environment variables:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Do not expose the service-role key with a `NEXT_PUBLIC_` variable.

## Mobile UX

The dashboard is intentionally dark, compact and vertically prioritized. Gamma remains a first-class section with horizontal scrolling rather than shrinking the table until values become unreadable.
