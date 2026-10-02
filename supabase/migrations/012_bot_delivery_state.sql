create table if not exists public.bot_delivery_state (
  channel text primary key,
  last_sent_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.bot_delivery_state enable row level security;
