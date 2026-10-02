alter table options_flow_snapshots
  add column if not exists gamma_table_path text,
  add column if not exists gamma_table_url text;
