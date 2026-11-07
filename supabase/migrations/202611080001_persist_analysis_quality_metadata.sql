-- Preserve the analysis source and quality notices so authenticated dashboards
-- can safely restore the most recent result after refresh or sign-in renewal.
begin;

alter table public.cost_analyses
  add column if not exists partial_data boolean not null default false,
  add column if not exists data_warnings jsonb not null default '[]'::jsonb
    check (jsonb_typeof(data_warnings) = 'array');

create or replace function public.persist_analysis_bundle(p_bundle jsonb) returns void
language plpgsql security definer set search_path = '' as $$
declare actor_id uuid := auth.uid();
declare org_id uuid := (p_bundle->>'target_org')::uuid;
declare analysis_id text := p_bundle->'analysis'->>'id';
declare decision_id text := p_bundle->'decision'->>'id';
declare warning_values jsonb := coalesce(p_bundle->'analysis'->'data_warnings', '[]'::jsonb);
begin
  if actor_id is null or not public.has_org_role(org_id, array['owner','admin','member']) then
    raise exception 'not_authorized' using errcode = '42501';
  end if;
  if jsonb_typeof(warning_values) <> 'array' then
    raise exception 'invalid_analysis_warnings' using errcode = '22023';
  end if;
  insert into public.cost_analyses(id, organization_id, user_id, source, anomaly, partial_data, data_warnings)
  values (analysis_id, org_id, actor_id, p_bundle->'analysis'->>'source', p_bundle->'analysis'->'anomaly',
    coalesce((p_bundle->'analysis'->>'partial_data')::boolean, false), warning_values)
  on conflict (organization_id, id) do nothing;
  insert into public.decision_traces(id, organization_id, user_id, analysis_id, trace)
  values (decision_id, org_id, actor_id, analysis_id, p_bundle->'decision'->'trace')
  on conflict (organization_id, id) do nothing;
  if jsonb_typeof(p_bundle->'approval') = 'object' then
    insert into public.approval_queue(id, organization_id, user_id, analysis_id, decision_id, service, environment,
      suggested_action, estimated_monthly_savings, is_simulated, created_at)
    values ((p_bundle->'approval'->>'id'), org_id, actor_id, (p_bundle->'approval'->>'analysis_id'),
      (p_bundle->'approval'->>'decision_id'), (p_bundle->'approval'->>'service'), (p_bundle->'approval'->>'environment'),
      (p_bundle->'approval'->>'suggested_action'), coalesce((p_bundle->'approval'->>'estimated_monthly_savings')::numeric, 0),
      coalesce((p_bundle->'approval'->>'is_simulated')::boolean, false), coalesce((p_bundle->'approval'->>'created_at')::timestamptz, now()))
    on conflict (organization_id, id) do nothing;
  end if;
  insert into public.investigation_reports(id, organization_id, user_id, analysis_id, decision_id, report, storage_path)
  values (p_bundle->'report'->>'id', org_id, actor_id, analysis_id, decision_id,
    p_bundle->'report'->'report', p_bundle->'report'->>'storage_path')
  on conflict (organization_id, id) do nothing;
  insert into public.audit_events(organization_id, actor_id, action, target_type, target_id, metadata)
  values (org_id, actor_id, 'analysis.persisted', 'cost_analysis', analysis_id,
    jsonb_build_object('source', p_bundle->'analysis'->>'source', 'partial_data',
      coalesce((p_bundle->'analysis'->>'partial_data')::boolean, false)));
end $$;

create or replace function public.cloudcost_sentinel_schema_version()
returns text
language sql stable security definer set search_path = '' as $$
  select case when
    (
      select count(*) = 16
      from unnest(array[
        'profiles','organizations','organization_members','scans','findings','approvals',
        'audit_events','reports','ai_usage_events','cost_analyses','decision_traces',
        'approval_queue','investigation_reports','aws_account_connections',
        'aws_cost_query_usage','workspace_finops_settings'
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
    and exists (select 1 from information_schema.columns c where c.table_schema = 'public'
      and c.table_name = 'cost_analyses' and c.column_name = 'partial_data' and c.is_nullable = 'NO')
    and exists (select 1 from information_schema.columns c where c.table_schema = 'public'
      and c.table_name = 'cost_analyses' and c.column_name = 'data_warnings' and c.is_nullable = 'NO')
  then 'cloudcost-sentinel-v6' else 'incomplete' end
$$;

notify pgrst, 'reload schema';
commit;
