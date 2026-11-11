-- Add tenant-authorized workspace export and a durable, de-identified lifecycle audit.
-- Account deletion is performed only by the separately authenticated Edge Function.
begin;

create table if not exists public.account_lifecycle_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  organization_id uuid references public.organizations(id) on delete set null,
  action text not null check (action in ('workspace.exported','account.deletion_requested','account.deletion_completed')),
  created_at timestamptz not null default now()
);
create index if not exists account_lifecycle_events_created_idx
  on public.account_lifecycle_events(created_at desc);
alter table public.account_lifecycle_events enable row level security;
revoke all on public.account_lifecycle_events from public, anon, authenticated;
grant select, insert, update on public.account_lifecycle_events to service_role;

-- A completed account deletion removes the user's personal workspace and records.
-- The Edge Function refuses deletion if the user is in a shared workspace.
alter table public.organizations drop constraint if exists organizations_created_by_fkey;
alter table public.organizations add constraint organizations_created_by_fkey
  foreign key (created_by) references auth.users(id) on delete cascade;
alter table public.scans drop constraint if exists scans_requested_by_fkey;
alter table public.scans add constraint scans_requested_by_fkey
  foreign key (requested_by) references auth.users(id) on delete cascade;
alter table public.approvals drop constraint if exists approvals_requested_by_fkey;
alter table public.approvals add constraint approvals_requested_by_fkey
  foreign key (requested_by) references auth.users(id) on delete cascade;
alter table public.reports drop constraint if exists reports_created_by_fkey;
alter table public.reports add constraint reports_created_by_fkey
  foreign key (created_by) references auth.users(id) on delete cascade;

alter table public.cost_analyses drop constraint if exists cost_analyses_user_id_fkey;
alter table public.cost_analyses add constraint cost_analyses_user_id_fkey
  foreign key (user_id) references auth.users(id) on delete cascade;
alter table public.decision_traces drop constraint if exists decision_traces_user_id_fkey;
alter table public.decision_traces add constraint decision_traces_user_id_fkey
  foreign key (user_id) references auth.users(id) on delete cascade;
alter table public.approval_queue drop constraint if exists approval_queue_user_id_fkey;
alter table public.approval_queue add constraint approval_queue_user_id_fkey
  foreign key (user_id) references auth.users(id) on delete cascade;
alter table public.investigation_reports drop constraint if exists investigation_reports_user_id_fkey;
alter table public.investigation_reports add constraint investigation_reports_user_id_fkey
  foreign key (user_id) references auth.users(id) on delete cascade;
alter table public.aws_account_connections drop constraint if exists aws_account_connections_updated_by_fkey;
alter table public.aws_account_connections alter column updated_by drop not null;
alter table public.aws_account_connections add constraint aws_account_connections_updated_by_fkey
  foreign key (updated_by) references auth.users(id) on delete set null;
alter table public.workspace_finops_settings drop constraint if exists workspace_finops_settings_updated_by_fkey;
alter table public.workspace_finops_settings alter column updated_by drop not null;
alter table public.workspace_finops_settings add constraint workspace_finops_settings_updated_by_fkey
  foreign key (updated_by) references auth.users(id) on delete set null;

create or replace function public.export_my_workspace(target_org uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  actor_id uuid := auth.uid();
  export_payload jsonb;
begin
  if actor_id is null or not public.has_org_role(target_org, array['owner','admin']) then
    raise exception 'not_authorized' using errcode = '42501';
  end if;

  insert into public.account_lifecycle_events(user_id, organization_id, action)
  values (actor_id, target_org, 'workspace.exported');

  select jsonb_build_object(
    'schema_version', 1,
    'exported_at', pg_catalog.now(),
    'requested_by', actor_id,
    'profile', (select to_jsonb(p) from public.profiles p where p.user_id = actor_id),
    'organization', (select to_jsonb(o) from public.organizations o where o.id = target_org),
    'memberships', coalesce((select jsonb_agg(to_jsonb(m)) from public.organization_members m where m.organization_id = target_org), '[]'::jsonb),
    'scans', coalesce((select jsonb_agg(to_jsonb(t)) from public.scans t where t.organization_id = target_org), '[]'::jsonb),
    'findings', coalesce((select jsonb_agg(to_jsonb(t)) from public.findings t where t.organization_id = target_org), '[]'::jsonb),
    'approvals', coalesce((select jsonb_agg(to_jsonb(t)) from public.approvals t where t.organization_id = target_org), '[]'::jsonb),
    'reports', coalesce((select jsonb_agg(to_jsonb(t)) from public.reports t where t.organization_id = target_org), '[]'::jsonb),
    'ai_usage_events', coalesce((select jsonb_agg(to_jsonb(t)) from public.ai_usage_events t where t.organization_id = target_org), '[]'::jsonb),
    'cost_analyses', coalesce((select jsonb_agg(to_jsonb(t)) from public.cost_analyses t where t.organization_id = target_org), '[]'::jsonb),
    'decision_traces', coalesce((select jsonb_agg(to_jsonb(t)) from public.decision_traces t where t.organization_id = target_org), '[]'::jsonb),
    'approval_queue', coalesce((select jsonb_agg(to_jsonb(t)) from public.approval_queue t where t.organization_id = target_org), '[]'::jsonb),
    'investigation_reports', coalesce((select jsonb_agg(to_jsonb(t)) from public.investigation_reports t where t.organization_id = target_org), '[]'::jsonb),
    'aws_account_connections', coalesce((select jsonb_agg(to_jsonb(t)) from public.aws_account_connections t where t.organization_id = target_org), '[]'::jsonb),
    'aws_cost_query_usage', coalesce((select jsonb_agg(to_jsonb(t)) from public.aws_cost_query_usage t where t.organization_id = target_org), '[]'::jsonb),
    'workspace_finops_settings', coalesce((select jsonb_agg(to_jsonb(t)) from public.workspace_finops_settings t where t.organization_id = target_org), '[]'::jsonb),
    'audit_events', coalesce((select jsonb_agg(to_jsonb(t)) from public.audit_events t where t.organization_id = target_org), '[]'::jsonb),
    'account_lifecycle_events', coalesce((select jsonb_agg(to_jsonb(t)) from public.account_lifecycle_events t where t.organization_id = target_org), '[]'::jsonb),
    'api_request_counters', coalesce((select jsonb_agg(to_jsonb(t)) from public.api_request_counters t where t.user_id = actor_id), '[]'::jsonb)
  ) into export_payload;

  return export_payload;
end $$;
revoke all on function public.export_my_workspace(uuid) from public, anon;
grant execute on function public.export_my_workspace(uuid) to authenticated;

create or replace function public.cloudcost_sentinel_schema_version()
returns text language sql stable security definer set search_path = '' as $$
  select case when
    (
      select count(*) = 18
      from unnest(array[
        'profiles','organizations','organization_members','scans','findings','approvals',
        'audit_events','reports','ai_usage_events','cost_analyses','decision_traces',
        'approval_queue','investigation_reports','aws_account_connections',
        'aws_cost_query_usage','workspace_finops_settings','api_request_counters','account_lifecycle_events'
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
    and not pg_catalog.has_table_privilege('authenticated', 'public.organization_members', 'INSERT')
    and not pg_catalog.has_table_privilege('authenticated', 'public.organization_members', 'UPDATE')
    and not pg_catalog.has_table_privilege('authenticated', 'public.organization_members', 'DELETE')
    and pg_catalog.has_table_privilege('service_role', 'public.account_lifecycle_events', 'INSERT')
    and pg_catalog.has_table_privilege('service_role', 'public.account_lifecycle_events', 'UPDATE')
    and exists (select 1 from pg_catalog.pg_policies p where p.schemaname = 'storage'
      and p.tablename = 'objects' and p.policyname = 'report_objects_member_select')
    and exists (select 1 from storage.buckets b where b.id = 'sentinel-reports' and not b.public)
    and pg_catalog.to_regprocedure('public.get_or_create_my_org()') is not null
    and pg_catalog.to_regprocedure('public.get_my_org_role(uuid)') is not null
    and pg_catalog.to_regprocedure('public.persist_analysis_bundle(jsonb)') is not null
    and pg_catalog.to_regprocedure('public.reserve_aws_cost_query(uuid,integer)') is not null
    and pg_catalog.to_regprocedure('public.admit_api_request(text)') is not null
    and pg_catalog.to_regprocedure('public.export_my_workspace(uuid)') is not null
    and exists (select 1 from information_schema.columns c where c.table_schema = 'public'
      and c.table_name = 'cost_analyses' and c.column_name = 'partial_data' and c.is_nullable = 'NO')
    and exists (select 1 from information_schema.columns c where c.table_schema = 'public'
      and c.table_name = 'cost_analyses' and c.column_name = 'data_warnings' and c.is_nullable = 'NO')
  then 'cloudcost-sentinel-v9' else 'incomplete' end
$$;

notify pgrst, 'reload schema';
commit;
