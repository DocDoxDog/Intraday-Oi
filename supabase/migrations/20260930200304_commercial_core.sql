create schema if not exists commercial;

create table if not exists commercial.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'ACTIVE' check (status in ('ACTIVE','SUSPENDED','CLOSED')),
  created_at timestamptz not null default now()
);

create table if not exists commercial.memberships (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'MEMBER' check (role in ('OWNER','ADMIN','MEMBER','BILLING','ANALYST')),
  status text not null default 'ACTIVE' check (status in ('ACTIVE','INVITED','SUSPENDED','REMOVED')),
  created_at timestamptz not null default now(),
  unique (organization_id, user_id)
);

create index if not exists commercial_memberships_user_idx
  on commercial.memberships(user_id, status);

create table if not exists commercial.plans (
  id text primary key,
  display_name text not null,
  description text,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

insert into commercial.plans(id, display_name, description)
values
  ('FREE','Free','Limited market intelligence access'),
  ('PRO','Pro','Core multi-factor market intelligence'),
  ('ADVANCED','Advanced','Deeper positioning, history and scenarios'),
  ('TEAM','Team','Shared organization workspace and administration'),
  ('API','API','Machine-readable intelligence access')
on conflict (id) do nothing;

create table if not exists commercial.subscriptions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  plan_id text not null references commercial.plans(id),
  provider text,
  provider_customer_id text,
  provider_subscription_id text,
  status text not null default 'PENDING' check (status in ('PENDING','TRIALING','ACTIVE','PAST_DUE','CANCELED','EXPIRED')),
  current_period_start timestamptz,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(provider, provider_subscription_id)
);

create index if not exists commercial_subscriptions_org_idx
  on commercial.subscriptions(organization_id, status);

create table if not exists commercial.entitlements (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  feature text not null,
  enabled boolean not null default false,
  effective_from timestamptz not null default now(),
  effective_to timestamptz,
  source text not null default 'subscription',
  metadata jsonb not null default '{}'::jsonb,
  unique(organization_id, feature)
);

create index if not exists commercial_entitlements_lookup_idx
  on commercial.entitlements(organization_id, feature, enabled);

create table if not exists commercial.notification_preferences (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  critical_news boolean not null default true,
  market_news boolean not null default true,
  oi_change boolean not null default false,
  gex_change boolean not null default false,
  plan_change boolean not null default true,
  morning_brief boolean not null default true,
  quiet_hours_start smallint,
  quiet_hours_end smallint,
  timezone text not null default 'Asia/Bangkok',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(organization_id, user_id)
);

create table if not exists commercial.market_access (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  symbol text not null,
  enabled boolean not null default true,
  effective_from timestamptz not null default now(),
  effective_to timestamptz,
  unique(organization_id, symbol)
);

create table if not exists commercial.api_keys (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  name text not null,
  key_prefix text not null,
  key_hash text not null unique,
  created_at timestamptz not null default now(),
  expires_at timestamptz,
  revoked_at timestamptz,
  last_used_at timestamptz
);

create index if not exists commercial_api_keys_org_idx
  on commercial.api_keys(organization_id, revoked_at);

create table if not exists commercial.usage_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  api_key_id uuid references commercial.api_keys(id) on delete set null,
  endpoint text not null,
  occurred_at timestamptz not null default now(),
  status_code integer,
  latency_ms integer,
  units integer not null default 1 check(units >= 0),
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists commercial_usage_org_time_idx
  on commercial.usage_events(organization_id, occurred_at desc);

create table if not exists commercial.audit_logs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references commercial.organizations(id) on delete set null,
  user_id uuid references auth.users(id) on delete set null,
  action text not null,
  target_type text,
  target_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists commercial_audit_org_time_idx
  on commercial.audit_logs(organization_id, created_at desc);

create table if not exists commercial.watchlists (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  symbols text[] not null default '{}',
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique(organization_id, user_id, name)
);

create table if not exists commercial.alerts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references commercial.organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  story_cluster_id text,
  alert_type text not null,
  severity text not null,
  dedupe_key text not null,
  status text not null default 'QUEUED' check (status in ('QUEUED','SENT','EDITED','MUTED','FAILED','EXPIRED')),
  telegram_chat_id text,
  telegram_message_id text,
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(organization_id, dedupe_key)
);

create index if not exists commercial_alerts_org_time_idx
  on commercial.alerts(organization_id, created_at desc);

alter table commercial.organizations enable row level security;
alter table commercial.memberships enable row level security;
alter table commercial.plans enable row level security;
alter table commercial.subscriptions enable row level security;
alter table commercial.entitlements enable row level security;
alter table commercial.notification_preferences enable row level security;
alter table commercial.market_access enable row level security;
alter table commercial.api_keys enable row level security;
alter table commercial.usage_events enable row level security;
alter table commercial.audit_logs enable row level security;
alter table commercial.watchlists enable row level security;
alter table commercial.alerts enable row level security;

revoke all on all tables in schema commercial from anon;
revoke all on commercial.api_keys from authenticated;
revoke all on commercial.usage_events from authenticated;
revoke all on commercial.audit_logs from authenticated;

grant usage on schema commercial to authenticated, service_role;
grant select on commercial.organizations, commercial.memberships, commercial.plans,
  commercial.subscriptions, commercial.entitlements, commercial.notification_preferences,
  commercial.market_access, commercial.watchlists, commercial.alerts to authenticated;
grant insert, update, delete on commercial.notification_preferences, commercial.watchlists to authenticated;
grant select on commercial.plans to authenticated;

grant all on all tables in schema commercial to service_role;

create policy commercial_org_select on commercial.organizations
  for select to authenticated
  using (exists (
    select 1 from commercial.memberships m
    where m.organization_id = organizations.id
      and m.user_id = (select auth.uid())
      and m.status = 'ACTIVE'
  ));

create policy commercial_membership_select on commercial.memberships
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy commercial_plan_select on commercial.plans
  for select to authenticated
  using (active = true);

create policy commercial_subscription_select on commercial.subscriptions
  for select to authenticated
  using (exists (
    select 1 from commercial.memberships m
    where m.organization_id = subscriptions.organization_id
      and m.user_id = (select auth.uid())
      and m.status = 'ACTIVE'
  ));

create policy commercial_entitlement_select on commercial.entitlements
  for select to authenticated
  using (exists (
    select 1 from commercial.memberships m
    where m.organization_id = entitlements.organization_id
      and m.user_id = (select auth.uid())
      and m.status = 'ACTIVE'
  ));

create policy commercial_notification_select on commercial.notification_preferences
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy commercial_notification_insert on commercial.notification_preferences
  for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from commercial.memberships m
      where m.organization_id = notification_preferences.organization_id
        and m.user_id = (select auth.uid())
        and m.status = 'ACTIVE'
    )
  );

create policy commercial_notification_update on commercial.notification_preferences
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy commercial_market_access_select on commercial.market_access
  for select to authenticated
  using (exists (
    select 1 from commercial.memberships m
    where m.organization_id = market_access.organization_id
      and m.user_id = (select auth.uid())
      and m.status = 'ACTIVE'
  ));

create policy commercial_watchlists_all on commercial.watchlists
  for all to authenticated
  using (
    user_id = (select auth.uid())
    and exists (
      select 1 from commercial.memberships m
      where m.organization_id = watchlists.organization_id
        and m.user_id = (select auth.uid())
        and m.status = 'ACTIVE'
    )
  )
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from commercial.memberships m
      where m.organization_id = watchlists.organization_id
        and m.user_id = (select auth.uid())
        and m.status = 'ACTIVE'
    )
  );

create policy commercial_alerts_select on commercial.alerts
  for select to authenticated
  using (exists (
    select 1 from commercial.memberships m
    where m.organization_id = alerts.organization_id
      and m.user_id = (select auth.uid())
      and m.status = 'ACTIVE'
  ));
