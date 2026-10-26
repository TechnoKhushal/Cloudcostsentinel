-- Initial tenant-scoped persistence schema for Supabase Postgres.
-- Apply only to a new/approved Supabase project after reviewing docs/SUPABASE_SETUP.md.
begin;

create table if not exists public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text check (char_length(display_name) <= 120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 120),
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table if not exists public.organization_members (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner','admin','member','reader')),
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);
create index if not exists organization_members_user_idx on public.organization_members(user_id, organization_id);

create table if not exists public.scans (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  requested_by uuid not null references auth.users(id) on delete restrict,
  source text not null check (source in ('synthetic','aws_cost_explorer','aws_read_only')),
  status text not null check (status in ('queued','running','completed','failed','cancelled')),
  started_at timestamptz,
  completed_at timestamptz,
  duration_ms integer check (duration_ms >= 0),
  coverage jsonb not null default '{}'::jsonb,
  error_summary text check (char_length(error_summary) <= 1000),
  idempotency_key text,
  created_at timestamptz not null default now(),
  unique (organization_id, idempotency_key)
);
create index if not exists scans_org_created_idx on public.scans(organization_id, created_at desc, id desc);
create index if not exists scans_org_status_idx on public.scans(organization_id, status, created_at desc);

create table if not exists public.findings (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  scan_id uuid not null references public.scans(id) on delete cascade,
  category text not null check (char_length(category) <= 80),
  severity text not null check (severity in ('info','low','medium','high','critical')),
  status text not null default 'open' check (status in ('open','acknowledged','resolved','dismissed')),
  resource_id text check (char_length(resource_id) <= 512),
  region text check (char_length(region) <= 80),
  title text not null check (char_length(title) between 1 and 240),
  evidence jsonb not null default '{}'::jsonb,
  confidence numeric(5,4) check (confidence between 0 and 1),
  cost_impact numeric(18,4) check (cost_impact >= 0),
  currency char(3) not null default 'USD',
  deduplication_key text not null,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (organization_id, deduplication_key),
  unique (organization_id, id),
  foreign key (organization_id, scan_id) references public.scans(organization_id, id) on delete cascade
);
create index if not exists findings_org_time_idx on public.findings(organization_id, created_at desc, id desc);
create index if not exists findings_org_severity_status_idx on public.findings(organization_id, severity, status, created_at desc);
create index if not exists findings_scan_idx on public.findings(scan_id, created_at desc);
create index if not exists findings_resource_idx on public.findings(organization_id, resource_id) where resource_id is not null;

create table if not exists public.approvals (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  finding_id uuid,
  requested_by uuid not null references auth.users(id) on delete restrict,
  status text not null default 'pending' check (status in ('pending','approved','rejected','cancelled')),
  reason text not null check (char_length(reason) between 1 and 2000),
  idempotency_key text not null,
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (organization_id, idempotency_key),
  foreign key (organization_id, finding_id) references public.findings(organization_id, id) on delete set null
);
create index if not exists approvals_org_status_idx on public.approvals(organization_id, status, created_at desc);

create table if not exists public.audit_events (
  id bigint generated always as identity primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  actor_id uuid references auth.users(id) on delete set null,
  action text not null check (char_length(action) between 1 and 120),
  target_type text check (char_length(target_type) <= 80),
  target_id text check (char_length(target_id) <= 160),
  metadata jsonb not null default '{}'::jsonb,
  request_id text check (char_length(request_id) <= 120),
  created_at timestamptz not null default now()
);
create index if not exists audit_events_org_time_idx on public.audit_events(organization_id, created_at desc, id desc);

create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  scan_id uuid references public.scans(id) on delete set null,
  created_by uuid not null references auth.users(id) on delete restrict,
  storage_path text not null unique,
  media_type text not null check (media_type in ('application/pdf','text/csv','application/json')),
  size_bytes bigint check (size_bytes between 0 and 20971520),
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (organization_id, scan_id) references public.scans(organization_id, id) on delete cascade
);
create index if not exists reports_org_time_idx on public.reports(organization_id, created_at desc);

create table if not exists public.ai_usage_events (
  id bigint generated always as identity primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  feature text not null check (char_length(feature) <= 80),
  model text not null check (char_length(model) <= 160),
  input_tokens integer check (input_tokens >= 0),
  output_tokens integer check (output_tokens >= 0),
  cost_usd numeric(18,8) check (cost_usd >= 0),
  latency_ms integer check (latency_ms >= 0),
  status text not null check (status in ('success','fallback','error','rate_limited')),
  request_id text check (char_length(request_id) <= 120),
  created_at timestamptz not null default now()
);
create index if not exists ai_usage_org_time_idx on public.ai_usage_events(organization_id, created_at desc);

-- updated_at trigger for mutable profile records.
create or replace function public.set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at before update on public.profiles for each row execute function public.set_updated_at();

-- Tenant membership helpers use the caller's Supabase JWT and cannot elevate roles.
create or replace function public.is_org_member(target_org uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.organization_members m where m.organization_id = target_org and m.user_id = (select auth.uid()))
$$;
create or replace function public.has_org_role(target_org uuid, allowed_roles text[]) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.organization_members m where m.organization_id = target_org and m.user_id = (select auth.uid()) and m.role = any(allowed_roles))
$$;
revoke all on function public.is_org_member(uuid) from public, anon;
revoke all on function public.has_org_role(uuid, text[]) from public, anon;
grant execute on function public.is_org_member(uuid) to authenticated;
grant execute on function public.has_org_role(uuid, text[]) to authenticated;

create or replace function public.add_organization_owner() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.organization_members (organization_id, user_id, role) values (new.id, new.created_by, 'owner');
  return new;
end $$;
drop trigger if exists organizations_add_owner on public.organizations;
create trigger organizations_add_owner after insert on public.organizations for each row execute function public.add_organization_owner();
revoke all on function public.add_organization_owner() from public, anon, authenticated;

alter table public.profiles enable row level security;
alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.scans enable row level security;
alter table public.findings enable row level security;
alter table public.approvals enable row level security;
alter table public.audit_events enable row level security;
alter table public.reports enable row level security;
alter table public.ai_usage_events enable row level security;

create policy profiles_self_select on public.profiles for select to authenticated using (user_id = (select auth.uid()));
create policy profiles_self_insert on public.profiles for insert to authenticated with check (user_id = (select auth.uid()));
create policy profiles_self_update on public.profiles for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy organizations_member_select on public.organizations for select to authenticated using (public.is_org_member(id));
create policy organizations_owner_insert on public.organizations for insert to authenticated with check (created_by = (select auth.uid()));
create policy organizations_admin_update on public.organizations for update to authenticated using (public.has_org_role(id, array['owner','admin'])) with check (public.has_org_role(id, array['owner','admin']));
create policy members_member_select on public.organization_members for select to authenticated using (public.is_org_member(organization_id));
create policy members_admin_insert on public.organization_members for insert to authenticated with check (public.has_org_role(organization_id, array['owner','admin']));
create policy members_admin_update on public.organization_members for update to authenticated using (public.has_org_role(organization_id, array['owner','admin'])) with check (public.has_org_role(organization_id, array['owner','admin']));
create policy members_owner_delete on public.organization_members for delete to authenticated using (public.has_org_role(organization_id, array['owner']));

create policy scans_member_select on public.scans for select to authenticated using (public.is_org_member(organization_id));
create policy scans_writer_insert on public.scans for insert to authenticated with check (requested_by = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin','member']));
create policy scans_writer_update on public.scans for update to authenticated using (public.has_org_role(organization_id, array['owner','admin','member'])) with check (public.has_org_role(organization_id, array['owner','admin','member']));
create policy findings_member_select on public.findings for select to authenticated using (public.is_org_member(organization_id));
create policy findings_writer_insert on public.findings for insert to authenticated with check (public.has_org_role(organization_id, array['owner','admin','member']));
create policy findings_writer_update on public.findings for update to authenticated using (public.has_org_role(organization_id, array['owner','admin','member'])) with check (public.has_org_role(organization_id, array['owner','admin','member']));
create policy approvals_member_select on public.approvals for select to authenticated using (public.is_org_member(organization_id));
create policy approvals_writer_insert on public.approvals for insert to authenticated with check (requested_by = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin','member']));
create policy approvals_reviewer_update on public.approvals for update to authenticated using (public.has_org_role(organization_id, array['owner','admin'])) with check (public.has_org_role(organization_id, array['owner','admin']) and reviewed_by = (select auth.uid()));
create policy audit_member_select on public.audit_events for select to authenticated using (public.is_org_member(organization_id));
create policy reports_member_select on public.reports for select to authenticated using (public.is_org_member(organization_id));
create policy reports_writer_insert on public.reports for insert to authenticated with check (created_by = (select auth.uid()) and public.has_org_role(organization_id, array['owner','admin','member']));
create policy reports_admin_delete on public.reports for delete to authenticated using (public.has_org_role(organization_id, array['owner','admin']));
create policy ai_usage_member_select on public.ai_usage_events for select to authenticated using (public.is_org_member(organization_id));

-- No direct updates/deletes on append-only audit and usage logs.
revoke update, delete on public.audit_events from authenticated;
revoke update, delete on public.ai_usage_events from authenticated;

revoke all on public.profiles, public.organizations, public.organization_members, public.scans,
  public.findings, public.approvals, public.audit_events, public.reports, public.ai_usage_events from anon;
grant select, insert, update on public.profiles to authenticated;
grant select, insert, update on public.organizations to authenticated;
grant select, insert, update, delete on public.organization_members to authenticated;
grant select, insert, update on public.scans to authenticated;
grant select, insert, update on public.findings to authenticated;
grant select, insert, update on public.approvals to authenticated;
grant select on public.audit_events to authenticated;
grant select, insert, delete on public.reports to authenticated;
grant select on public.ai_usage_events to authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('sentinel-reports', 'sentinel-reports', false, 20971520, array['application/pdf','text/csv','application/json'])
on conflict (id) do update set public = false, file_size_limit = 20971520, allowed_mime_types = excluded.allowed_mime_types;
create policy report_objects_member_select on storage.objects for select to authenticated
  using (bucket_id = 'sentinel-reports' and public.is_org_member(((storage.foldername(name))[1])::uuid));
create policy report_objects_writer_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'sentinel-reports' and public.has_org_role(((storage.foldername(name))[1])::uuid, array['owner','admin','member']));
create policy report_objects_admin_delete on storage.objects for delete to authenticated
  using (bucket_id = 'sentinel-reports' and public.has_org_role(((storage.foldername(name))[1])::uuid, array['owner','admin']));

commit;
