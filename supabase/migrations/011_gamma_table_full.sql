alter table public.options_flow_snapshots
  add column if not exists gamma_table_full_path text,
  add column if not exists gamma_table_full_url text;
