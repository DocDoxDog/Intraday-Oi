create table if not exists public.news_announcements (
  id bigserial primary key,
  source text not null,
  external_id text not null,
  headline text not null,
  summary text,
  url text not null,
  published_at timestamptz,
  detected_at timestamptz not null,
  category text not null,
  relevance text not null,
  rights_status text not null,
  created_at timestamptz not null default now(),
  unique(source, external_id)
);

create index if not exists idx_news_announcements_published_at
  on public.news_announcements(published_at desc);

create index if not exists idx_news_announcements_relevance
  on public.news_announcements(relevance, published_at desc);

alter table public.news_announcements enable row level security;
