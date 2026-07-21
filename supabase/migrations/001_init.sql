create table options_flow_snapshots (
  id bigserial primary key,
  captured_at timestamptz default now(),
  contract text,
  future_price numeric,
  future_chg numeric,
  put_volume int,
  call_volume int,
  vol numeric,
  vol_chg numeric,
  delta_levels jsonb,
  raw_series jsonb,
  ai_summary text
);

alter table options_flow_snapshots enable row level security;
-- ไม่มี policy ให้ anon/public — เข้าถึงได้เฉพาะผ่าน service role key เท่านั้น
