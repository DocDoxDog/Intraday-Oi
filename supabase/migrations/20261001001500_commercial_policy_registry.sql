create table if not exists commercial.data_source_policies (
  source text primary key,
  access_method text not null,
  rights_status text not null,
  commercial_use boolean not null default false,
  redistribution boolean not null default false,
  attribution_required boolean not null default true,
  retention_days integer,
  agreement_reference text,
  effective_from date not null default current_date,
  effective_to date,
  notes text
);

create table if not exists commercial.regulatory_profiles (
  id uuid primary key default gen_random_uuid(),
  jurisdiction text not null,
  customer_type text not null,
  feature text not null,
  enabled boolean not null default false,
  legal_review_status text not null default 'LEGAL_REVIEW_REQUIRED',
  required_disclosures jsonb not null default '[]'::jsonb,
  effective_from timestamptz not null default now(),
  effective_to timestamptz,
  unique(jurisdiction, customer_type, feature, effective_from)
);

create table if not exists commercial.cfd_mappings (
  id uuid primary key default gen_random_uuid(),
  broker text not null,
  cfd_symbol text not null,
  canonical_reference text not null,
  mapping_version text not null,
  effective_from timestamptz not null,
  effective_to timestamptz,
  unique(broker, cfd_symbol, mapping_version)
);

alter table commercial.data_source_policies enable row level security;
alter table commercial.regulatory_profiles enable row level security;
alter table commercial.cfd_mappings enable row level security;

revoke all on commercial.data_source_policies,
  commercial.regulatory_profiles,
  commercial.cfd_mappings
  from anon, authenticated;

grant all on commercial.data_source_policies,
  commercial.regulatory_profiles,
  commercial.cfd_mappings
  to service_role;

drop policy if exists commercial_notification_update on commercial.notification_preferences;

create policy commercial_notification_update on commercial.notification_preferences
  for update to authenticated
  using (
    user_id = (select auth.uid())
    and exists (
      select 1 from commercial.memberships m
      where m.organization_id = notification_preferences.organization_id
        and m.user_id = (select auth.uid())
        and m.status = 'ACTIVE'
    )
  )
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from commercial.memberships m
      where m.organization_id = notification_preferences.organization_id
        and m.user_id = (select auth.uid())
        and m.status = 'ACTIVE'
    )
  );
