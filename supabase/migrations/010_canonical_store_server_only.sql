-- Canonical store is server-side only.
-- The tables stay in public for the current Supabase Data API client, but
-- browser-facing roles receive no table privileges.
revoke all on table public.oi_core_dataset_versions from anon, authenticated;
revoke all on table public.oi_core_raw_market_data from anon, authenticated;
revoke all on table public.oi_core_instruments from anon, authenticated;
revoke all on table public.oi_core_futures from anon, authenticated;
revoke all on table public.oi_core_expirations from anon, authenticated;
revoke all on table public.oi_core_strikes from anon, authenticated;
revoke all on table public.oi_core_options from anon, authenticated;
revoke all on table public.oi_core_option_quotes from anon, authenticated;
revoke all on table public.oi_core_option_trades from anon, authenticated;
revoke all on table public.oi_core_option_oi from anon, authenticated;
revoke all on table public.oi_core_greek_observations from anon, authenticated;
revoke all on table public.oi_core_gex_snapshots from anon, authenticated;
revoke all on table public.oi_core_dex_snapshots from anon, authenticated;
revoke all on table public.oi_core_market_states from anon, authenticated;
