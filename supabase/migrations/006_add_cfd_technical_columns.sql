-- Add direct storage for Twelve Data spot/basis conversion and hidden
-- multi-timeframe technical confirmation.
-- Safe to run more than once.

alter table options_flow_snapshots
  add column if not exists spot_price numeric,
  add column if not exists basis_diff numeric,
  add column if not exists cfd_price numeric,
  add column if not exists price_conversion jsonb,
  add column if not exists technical_context jsonb;

comment on column options_flow_snapshots.spot_price is
  'Latest Twelve Data XAU/USD spot price used for basis conversion';
comment on column options_flow_snapshots.basis_diff is
  'QuikStrike Futures price minus Twelve Data Spot price';
comment on column options_flow_snapshots.cfd_price is
  'Spot-equivalent CFD price for this snapshot';
comment on column options_flow_snapshots.price_conversion is
  'Audit metadata and formula for Futures-to-CFD conversion';
comment on column options_flow_snapshots.technical_context is
  'Internal H4/H1/M15/M5/M1 EMA and price-action confirmation context';
