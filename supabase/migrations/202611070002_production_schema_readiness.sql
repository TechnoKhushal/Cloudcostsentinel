-- Expose a non-sensitive schema/version probe so Render fails closed when
-- Supabase migrations, RLS policies, or the private report bucket are missing.
begin;

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
        and c.relnamespace = 'public'::pg_catalog.regnamespace
        and c.relrowsecurity
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
      join pg_catalog.pg_policies p on p.schemaname = 'public'
        and p.policyname = expected.policy_name
    )
    and exists (
      select 1 from pg_catalog.pg_policies p
      where p.schemaname = 'storage' and p.tablename = 'objects'
        and p.policyname = 'report_objects_member_select'
    )
    and exists (select 1 from storage.buckets b where b.id = 'sentinel-reports' and not b.public)
    and pg_catalog.to_regprocedure('public.get_or_create_my_org()') is not null
    and pg_catalog.to_regprocedure('public.get_my_org_role(uuid)') is not null
    and pg_catalog.to_regprocedure('public.persist_analysis_bundle(jsonb)') is not null
    and pg_catalog.to_regprocedure('public.reserve_aws_cost_query(uuid,integer)') is not null
  then 'cloudcost-sentinel-v5'
  else 'incomplete'
  end
$$;
revoke all on function public.cloudcost_sentinel_schema_version() from public, anon, authenticated;
grant execute on function public.cloudcost_sentinel_schema_version() to anon;
notify pgrst, 'reload schema';

commit;
