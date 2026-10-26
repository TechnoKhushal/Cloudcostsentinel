-- Runtime records consumed by the current FastAPI analysis/approval API.
begin;

create table if not exists public.cost_analyses (
  id text primary key check (char_length(id) between 1 and 160),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete restrict,
  source text not null check (source in ('synthetic_scenario','aws_cost_explorer','custom_supplied')),
  anomaly jsonb not null,
  created_at timestamptz not null default now(),
  unique (organization_id, id)
);
create index if not exists cost_analyses_org_created_idx on public.cost_analyses(organization_id, created_at desc, id desc);

create table if not exists public.decision_traces (
  id text primary key check (char_length(id) between 1 and 160),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete restrict,
  analysis_id text not null,
  trace jsonb not null,
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (organization_id, analysis_id) references public.cost_analyses(organization_id, id) on delete cascade
);
create index if not exists decision_traces_org_created_idx on public.decision_traces(organization_id, created_at desc, id desc);

create table if not exists public.approval_queue (
  id text primary key check (char_length(id) between 1 and 160),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete restrict,
  analysis_id text not null,
  decision_id text not null,
  service text not null check (char_length(service) <= 200),
  environment text not null check (char_length(environment) <= 100),
  suggested_action text not null check (char_length(suggested_action) <= 2000),
  estimated_monthly_savings numeric(18,4) not null default 0 check (estimated_monthly_savings >= 0),
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  notes text check (char_length(notes) <= 1000),
  is_simulated boolean not null default false,
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (organization_id, analysis_id) references public.cost_analyses(organization_id, id) on delete cascade,
  foreign key (organization_id, decision_id) references public.decision_traces(organization_id, id) on delete cascade
);
create index if not exists approval_queue_org_status_idx on public.approval_queue(organization_id, status, created_at desc, id desc);

create table if not exists public.investigation_reports (
  id text primary key check (char_length(id) between 1 and 160),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete restrict,
  analysis_id text not null,
  decision_id text not null,
  report jsonb not null,
  storage_path text unique,
  storage_status text not null default 'ready' check (storage_status in ('ready','missing')),
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  check (storage_path is null or (storage_path not like '%..%' and split_part(storage_path, '/', 1) = organization_id::text)),
  foreign key (organization_id, analysis_id) references public.cost_analyses(organization_id, id) on delete cascade,
  foreign key (organization_id, decision_id) references public.decision_traces(organization_id, id) on delete cascade
);
create index if not exists investigation_reports_org_created_idx on public.investigation_reports(organization_id, created_at desc, id desc);

alter table public.cost_analyses enable row level security;
alter table public.decision_traces enable row level security;
alter table public.approval_queue enable row level security;
alter table public.investigation_reports enable row level security;

create policy cost_analyses_member_select on public.cost_analyses for select to authenticated using (public.is_org_member(organization_id));
create policy cost_analyses_member_insert on public.cost_analyses for insert to authenticated with check (user_id = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin','member']));
create policy decision_traces_member_select on public.decision_traces for select to authenticated using (public.is_org_member(organization_id));
create policy decision_traces_member_insert on public.decision_traces for insert to authenticated with check (user_id = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin','member']));
create policy approval_queue_member_select on public.approval_queue for select to authenticated using (public.is_org_member(organization_id));
create policy approval_queue_member_insert on public.approval_queue for insert to authenticated with check (user_id = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin','member']));
create policy approval_queue_reviewer_update on public.approval_queue for update to authenticated using (public.has_org_role(organization_id, array['owner','admin','reviewer'])) with check (public.has_org_role(organization_id, array['owner','admin','reviewer']) and reviewed_by = (select auth.uid()));
create policy investigation_reports_member_select on public.investigation_reports for select to authenticated using (public.is_org_member(organization_id));
create policy investigation_reports_member_insert on public.investigation_reports for insert to authenticated with check (user_id = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin','member']));

revoke all on public.cost_analyses, public.decision_traces, public.approval_queue, public.investigation_reports from anon;
grant select, insert on public.cost_analyses to authenticated;
grant select, insert on public.decision_traces to authenticated;
grant select, insert, update on public.approval_queue to authenticated;
grant select, insert on public.investigation_reports to authenticated;

create or replace function public.get_or_create_my_org() returns uuid
language plpgsql security definer set search_path = '' as $$
declare current_user_id uuid := auth.uid();
declare existing_org uuid;
declare new_org uuid;
begin
  if current_user_id is null then raise exception 'not_authenticated' using errcode = '28000'; end if;
  perform pg_advisory_xact_lock(hashtextextended(current_user_id::text, 0));
  insert into public.profiles(user_id) values (current_user_id) on conflict (user_id) do nothing;
  select m.organization_id into existing_org from public.organization_members m
    join public.organizations o on o.id = m.organization_id
    where m.user_id = current_user_id and o.deleted_at is null
    order by m.created_at asc limit 1;
  if existing_org is not null then return existing_org; end if;
  insert into public.organizations(name, created_by) values ('My workspace', current_user_id) returning id into new_org;
  -- Migration 001's SECURITY DEFINER organization trigger adds this user as owner.
  return new_org;
end $$;
create or replace function public.get_my_org_role(target_org uuid) returns text
language sql stable security definer set search_path = '' as $$
  select m.role from public.organization_members m where m.organization_id = target_org and m.user_id = (select auth.uid()) limit 1
$$;
create or replace function public.persist_analysis_bundle(p_bundle jsonb) returns void
language plpgsql security definer set search_path = '' as $$
declare actor_id uuid := auth.uid();
declare org_id uuid := (p_bundle->>'target_org')::uuid;
declare analysis_id text := p_bundle->'analysis'->>'id';
declare decision_id text := p_bundle->'decision'->>'id';
begin
  if actor_id is null or not public.has_org_role(org_id, array['owner','admin','member']) then
    raise exception 'not_authorized' using errcode = '42501';
  end if;
  insert into public.cost_analyses(id, organization_id, user_id, source, anomaly)
  values (analysis_id, org_id, actor_id, p_bundle->'analysis'->>'source', p_bundle->'analysis'->'anomaly')
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
  values (p_bundle->'report'->>'id', org_id, actor_id, analysis_id, decision_id, p_bundle->'report'->'report', p_bundle->'report'->>'storage_path')
  on conflict (organization_id, id) do nothing;
  insert into public.audit_events(organization_id, actor_id, action, target_type, target_id, metadata)
  values (org_id, actor_id, 'analysis.persisted', 'cost_analysis', analysis_id,
    jsonb_build_object('source', p_bundle->'analysis'->>'source'));
end $$;
revoke all on function public.get_or_create_my_org() from public, anon;
revoke all on function public.get_my_org_role(uuid) from public, anon;
revoke all on function public.persist_analysis_bundle(jsonb) from public, anon;
grant execute on function public.get_or_create_my_org() to authenticated;
grant execute on function public.get_my_org_role(uuid) to authenticated;
grant execute on function public.persist_analysis_bundle(jsonb) to authenticated;

commit;
