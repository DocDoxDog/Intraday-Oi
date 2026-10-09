alter table public.news_announcements
  add column if not exists event_time timestamptz,
  add column if not exists actual text,
  add column if not exists forecast text,
  add column if not exists previous text,
  add column if not exists event_status text not null default 'UNKNOWN',
  add column if not exists calendar_data_status text not null default 'UNKNOWN',
  add column if not exists actual_source text,
  add column if not exists forecast_source text,
  add column if not exists previous_source text,
  add column if not exists calendar_retrieved_at timestamptz;

create index if not exists idx_news_announcements_event_time
  on public.news_announcements(event_time desc);

create index if not exists idx_news_announcements_event_status
  on public.news_announcements(event_status, event_time desc);

comment on column public.news_announcements.actual is
  'Source-backed economic-calendar Actual value; NULL means not released or not verified.';

comment on column public.news_announcements.forecast is
  'Source-backed economic-calendar Forecast value; NULL means not published or not meaningful for the event.';

comment on column public.news_announcements.previous is
  'Source-backed economic-calendar Previous value; NULL means not published or not verified.';

comment on column public.news_announcements.calendar_data_status is
  'Provenance state for calendar enrichment, e.g. HTML_ENRICHED or JSON_ONLY.';

comment on column public.news_announcements.event_status is
  'RELEASED, UPCOMING, UNKNOWN, or SCHEDULED based on source fields and event time.';
