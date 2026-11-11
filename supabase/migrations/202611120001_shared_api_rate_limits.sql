-- Add authenticated, cross-instance API rate limits using the existing Supabase database.
begin;

create table if not exists public.api_request_counters (
  user_id uuid not null references auth.users(id) on delete cascade,
  bucket text not null check (bucket in ('default','analysis','aws_verify')),
  window_started_at timestamptz not null,
  request_count integer not null check (request_count > 0),
  primary key (user_id, bucket)
);

alter table public.api_request_counters enable row level security;
revoke all on public.api_request_counters from public, anon, authenticated;

create or replace function public.admit_api_request(p_bucket text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
  actor_id uuid := auth.uid();
  next_count integer;
  max_requests integer;
  window_seconds integer := 60;
begin
  if actor_id is null or not exists (
    select 1 from public.organization_members m
      join public.organizations o on o.id = m.organization_id
      where m.user_id = actor_id and o.deleted_at is null
  ) then
    raise exception 'not_authorized' using errcode = '42501';
  end if;
  if p_bucket is null or p_bucket not in ('default','analysis','aws_verify') then
    raise exception 'invalid_rate_limit' using errcode = '22023';
  end if;
  max_requests := case p_bucket when 'analysis' then 5 when 'aws_verify' then 3 else 120 end;

  insert into public.api_request_counters(user_id, bucket, window_started_at, request_count)
  values (actor_id, p_bucket, now(), 1)
  on conflict (user_id, bucket) do update set
    request_count = case
      when public.api_request_counters.window_started_at <= now() - pg_catalog.make_interval(secs => window_seconds) then 1
      else least(public.api_request_counters.request_count + 1, max_requests + 1)
    end,
    window_started_at = case
      when public.api_request_counters.window_started_at <= now() - pg_catalog.make_interval(secs => window_seconds) then now()
      else public.api_request_counters.window_started_at
    end
  returning request_count into next_count;

  return next_count <= max_requests;
end $$;

revoke all on function public.admit_api_request(text) from public, anon;
grant execute on function public.admit_api_request(text) to authenticated;

create or replace function public.cloudcost_sentinel_schema_version()
returns text language sql stable security definer set search_path = '' as $$
  select case when
    (
      select count(*) = 17
      from unnest(array[
        'profiles','organizations','organization_members','scans','findings','approvals',
        'audit_events','reports','ai_usage_events','cost_analyses','decision_traces',
        'approval_queue','investigation_reports','aws_account_connections',
        'aws_cost_query_usage','workspace_finops_settings','api_request_counters'
      ]::text[]) as expected(table_name)
      join pg_catalog.pg_class c on c.relname = expected.table_name
        and c.relnamespace = 'public'::pg_catalog.regnamespace and c.relrowsecurity
    )
    and (
      select count(*) = 15
      from unnest(array[
        'profiles_self_select','organizations_member_select','members_member_select',
        'scans_member_select','findings_member_select','approvals_member_select',
        'audit_member_select','reports_member_select','ai_usage_member_select',
        'cost_analyses_member_select','decision_traces_member_select',
        'approval_queue_member_select','investigation_reports_member_select',
        'aws_connections_admin_update','finops_settings_admin_update'
      ]::text[]) as expected(policy_name)
      join pg_catalog.pg_policies p on p.schemaname = 'public' and p.policyname = expected.policy_name
    )
    and exists (select 1 from pg_catalog.pg_policies p where p.schemaname = 'storage'
      and p.tablename = 'objects' and p.policyname = 'report_objects_member_select')
    and exists (select 1 from storage.buckets b where b.id = 'sentinel-reports' and not b.public)
    and pg_catalog.to_regprocedure('public.get_or_create_my_org()') is not null
    and pg_catalog.to_regprocedure('public.get_my_org_role(uuid)') is not null
    and pg_catalog.to_regprocedure('public.persist_analysis_bundle(jsonb)') is not null
    and pg_catalog.to_regprocedure('public.reserve_aws_cost_query(uuid,integer)') is not null
    and pg_catalog.to_regprocedure('public.admit_api_request(text)') is not null
    and exists (select 1 from information_schema.columns c where c.table_schema = 'public'
      and c.table_name = 'cost_analyses' and c.column_name = 'partial_data' and c.is_nullable = 'NO')
    and exists (select 1 from information_schema.columns c where c.table_schema = 'public'
      and c.table_name = 'cost_analyses' and c.column_name = 'data_warnings' and c.is_nullable = 'NO')
  then 'cloudcost-sentinel-v7' else 'incomplete' end
$$;

revoke all on function public.cloudcost_sentinel_schema_version() from public, anon, authenticated;
grant execute on function public.cloudcost_sentinel_schema_version() to anon;
notify pgrst, 'reload schema';
commit;
