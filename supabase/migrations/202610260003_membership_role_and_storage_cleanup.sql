-- Forward-compatible additions; keep previously released migrations immutable.
begin;

alter table public.organization_members
  drop constraint if exists organization_members_role_check;
alter table public.organization_members
  add constraint organization_members_role_check
  check (role in ('owner','admin','member','reviewer','reader'));

drop policy if exists report_objects_owner_delete on storage.objects;
create policy report_objects_owner_delete on storage.objects for delete to authenticated
  using (bucket_id = 'sentinel-reports' and owner_id = (select auth.uid())::text
    and public.is_org_member(((storage.foldername(name))[1])::uuid));

commit;
