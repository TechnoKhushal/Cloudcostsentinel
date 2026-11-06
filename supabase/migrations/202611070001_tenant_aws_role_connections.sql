-- Per-workspace AWS billing access through customer-owned, read-only IAM roles.
-- Apply after 202610260003_membership_role_and_storage_cleanup.sql.
begin;

create table if not exists public.aws_account_connections (
  organization_id uuid primary key references public.organizations(id) on delete cascade,
  role_arn text not null check (
    role_arn ~ '^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/CloudCostSentinelReadOnly$'
  ),
  external_id text not null unique check (external_id ~ '^[A-Fa-f0-9]{32}$'),
  account_id char(12) not null check (account_id ~ '^[0-9]{12}$'),
  status text not null default 'pending' check (status in ('pending','connected','error')),
  verified_at timestamptz,
  updated_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists aws_account_connections_status_idx
  on public.aws_account_connections(status, updated_at desc);
alter table public.aws_account_connections enable row level security;
create policy aws_connections_member_select on public.aws_account_connections
  for select to authenticated using (public.is_org_member(organization_id));
create policy aws_connections_admin_insert on public.aws_account_connections
  for insert to authenticated with check (
    updated_by = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin'])
  );
create policy aws_connections_admin_update on public.aws_account_connections
  for update to authenticated using (public.has_org_role(organization_id, array['owner','admin']))
  with check (updated_by = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin']));
create policy aws_connections_admin_delete on public.aws_account_connections
  for delete to authenticated using (public.has_org_role(organization_id, array['owner','admin']));
revoke all on public.aws_account_connections from anon;
grant select, insert, update, delete on public.aws_account_connections to authenticated;

-- One durable counter per workspace bounds AWS's metered API usage across all
-- Render processes. It records at most 20 Cost Explorer calls/day by default.
create table if not exists public.aws_cost_query_usage (
  organization_id uuid primary key references public.organizations(id) on delete cascade,
  usage_day date not null,
  request_count integer not null check (request_count >= 0),
  updated_at timestamptz not null default now()
);
alter table public.aws_cost_query_usage enable row level security;
revoke all on public.aws_cost_query_usage from anon, authenticated;

create or replace function public.reserve_aws_cost_query(p_organization_id uuid, p_daily_limit integer)
returns boolean language plpgsql security definer set search_path = '' as $$
declare next_count integer;
begin
  if auth.uid() is null or not public.is_org_member(p_organization_id) then
    raise exception 'not_authorized' using errcode = '42501';
  end if;
  if p_daily_limit < 1 or p_daily_limit > 1000 then
    raise exception 'invalid_limit' using errcode = '22023';
  end if;
  insert into public.aws_cost_query_usage(organization_id, usage_day, request_count)
  values (p_organization_id, (now() at time zone 'utc')::date, 1)
  on conflict (organization_id) do update set
    usage_day = (now() at time zone 'utc')::date,
    request_count = case when public.aws_cost_query_usage.usage_day = (now() at time zone 'utc')::date
      then least(public.aws_cost_query_usage.request_count + 1, p_daily_limit + 1) else 1 end,
    updated_at = now()
  returning request_count into next_count;
  return next_count <= p_daily_limit;
end $$;
revoke all on function public.reserve_aws_cost_query(uuid, integer) from public, anon;
grant execute on function public.reserve_aws_cost_query(uuid, integer) to authenticated;

create or replace function public.set_aws_account_connection_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at = now(); return new; end $$;
create trigger aws_account_connections_set_updated_at
  before update on public.aws_account_connections
  for each row execute function public.set_aws_account_connection_updated_at();
revoke all on function public.set_aws_account_connection_updated_at() from public, anon, authenticated;

create table if not exists public.workspace_finops_settings (
  organization_id uuid primary key references public.organizations(id) on delete cascade,
  monthly_budget numeric(18,2) not null check (monthly_budget > 0),
  currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
  updated_by uuid not null references auth.users(id) on delete restrict,
  updated_at timestamptz not null default now()
);
alter table public.workspace_finops_settings enable row level security;
create policy finops_settings_member_select on public.workspace_finops_settings
  for select to authenticated using (public.is_org_member(organization_id));
create policy finops_settings_admin_insert on public.workspace_finops_settings
  for insert to authenticated with check (
    updated_by = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin'])
  );
create policy finops_settings_admin_update on public.workspace_finops_settings
  for update to authenticated using (public.has_org_role(organization_id, array['owner','admin']))
  with check (updated_by = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin']));
revoke all on public.workspace_finops_settings from anon;
grant select, insert, update on public.workspace_finops_settings to authenticated;
create trigger workspace_finops_settings_set_updated_at
  before update on public.workspace_finops_settings
  for each row execute function public.set_aws_account_connection_updated_at();

commit;
