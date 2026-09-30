create table if not exists commercial.saved_plans (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  scenario_id text,
  name text not null,
  payload jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists commercial_saved_plans_org_idx
  on commercial.saved_plans(organization_id, created_at desc);

create table if not exists commercial.alert_deliveries (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  alert_id uuid not null references commercial.alerts(id) on delete cascade,
  channel text not null,
  destination text,
  provider_message_id text,
  attempt integer not null default 1 check(attempt > 0),
  status text not null default 'QUEUED' check(status in ('QUEUED','SENT','EDITED','FAILED','SKIPPED')),
  sent_at timestamptz,
  error_code text,
  created_at timestamptz not null default now()
);

create index if not exists commercial_alert_deliveries_alert_idx
  on commercial.alert_deliveries(alert_id, created_at desc);

create table if not exists commercial.feedback (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  entity_type text not null check(entity_type in ('ALERT','NEWS','ANALYSIS','PLAN')),
  entity_id text not null,
  feedback_type text not null check(feedback_type in ('USEFUL','NOT_USEFUL','TOO_MANY','NOT_RELEVANT')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists commercial_feedback_org_time_idx
  on commercial.feedback(organization_id, created_at desc);

create table if not exists commercial.product_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references commercial.organizations(id) on delete set null,
  user_id uuid references auth.users(id) on delete set null,
  event_name text not null,
  channel text not null,
  occurred_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists commercial_product_events_org_time_idx
  on commercial.product_events(organization_id, occurred_at desc);

create table if not exists commercial.payment_webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  provider_event_id text not null,
  event_type text not null,
  signature_valid boolean not null,
  payload_hash text not null,
  processed_at timestamptz,
  status text not null default 'RECEIVED' check(status in ('RECEIVED','PROCESSED','IGNORED','FAILED')),
  created_at timestamptz not null default now(),
  unique(provider, provider_event_id)
);

create index if not exists commercial_payment_events_provider_idx
  on commercial.payment_webhook_events(provider, created_at desc);

alter table commercial.notification_preferences
  add column if not exists alert_policy jsonb not null default '{
    "max_alerts_per_hour": 6,
    "max_news_alerts_per_day": 20,
    "cooldown_minutes": 15,
    "same_story_cooldown_minutes": 60,
    "severity_threshold": "HIGH",
    "digest_interval_minutes": 30
  }'::jsonb;

alter table commercial.saved_plans enable row level security;
alter table commercial.alert_deliveries enable row level security;
alter table commercial.feedback enable row level security;
alter table commercial.product_events enable row level security;
alter table commercial.payment_webhook_events enable row level security;

revoke all on commercial.saved_plans, commercial.alert_deliveries, commercial.feedback,
  commercial.product_events, commercial.payment_webhook_events
  from anon, authenticated;

grant all on commercial.saved_plans, commercial.alert_deliveries, commercial.feedback,
  commercial.product_events, commercial.payment_webhook_events
  to service_role;

create policy commercial_saved_plans_select on commercial.saved_plans
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy commercial_saved_plans_write on commercial.saved_plans
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from commercial.memberships m
      where m.organization_id = saved_plans.organization_id
        and m.user_id = (select auth.uid())
        and m.status = 'ACTIVE'
    )
  );

create policy commercial_feedback_select on commercial.feedback
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy commercial_feedback_insert on commercial.feedback
  for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from commercial.memberships m
      where m.organization_id = feedback.organization_id
        and m.user_id = (select auth.uid())
        and m.status = 'ACTIVE'
    )
  );
