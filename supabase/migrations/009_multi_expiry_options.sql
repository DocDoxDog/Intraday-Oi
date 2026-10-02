-- Canonical multi-expiration option observations.
-- Existing options_flow_snapshots remains the raw/legacy snapshot store.

create table if not exists option_expirations (
  id bigserial primary key,
  product_symbol text not null,
  expiry_code text not null,
  expiry_date date,
  observed_at timestamptz not null,
  dte numeric,
  source text not null default 'cme_quikstrike',
  source_snapshot_id bigint references options_flow_snapshots(id) on delete set null,
  created_at timestamptz not null default now(),
  unique(product_symbol, expiry_code, observed_at)
);

create index if not exists idx_option_expirations_product_dte
  on option_expirations(product_symbol, dte);

create table if not exists option_strike_observations (
  id bigserial primary key,
  expiration_id bigint not null references option_expirations(id) on delete cascade,
  strike numeric not null,
  call_oi numeric,
  put_oi numeric,
  call_iv numeric,
  put_iv numeric,
  call_delta numeric,
  put_delta numeric,
  gamma numeric,
  call_gex numeric,
  put_gex numeric,
  net_gex numeric,
  observed_at timestamptz not null,
  created_at timestamptz not null default now(),
  unique(expiration_id, strike)
);

create index if not exists idx_option_strike_observations_expiry_strike
  on option_strike_observations(expiration_id, strike);

create index if not exists idx_option_strike_observations_observed
  on option_strike_observations(observed_at);

alter table option_expirations enable row level security;
alter table option_strike_observations enable row level security;

-- No anon/public policies. Service role owns ingestion and reads.
