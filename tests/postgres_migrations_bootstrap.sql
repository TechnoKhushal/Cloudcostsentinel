-- Minimal Supabase auth/storage interfaces for exercising migrations on Postgres.
-- This is not a replacement for testing against an actual Supabase project.
create role authenticated;
create role anon;

create schema auth;
create table auth.users(id uuid primary key);
create or replace function auth.uid() returns uuid
language sql stable
as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to authenticated;
grant execute on function auth.uid() to authenticated;

create schema storage;
create table storage.buckets(
  id text primary key,
  name text not null,
  public boolean not null,
  file_size_limit bigint,
  allowed_mime_types text[]
);
create table storage.objects(
  id bigint generated always as identity primary key,
  bucket_id text not null references storage.buckets(id),
  name text not null,
  owner_id text
);
create or replace function storage.foldername(name text) returns text[]
language sql immutable
as $$ select string_to_array(name, '/') $$;
grant usage on schema storage to authenticated;
grant select, insert, delete on storage.objects to authenticated;
grant select on storage.buckets to authenticated;

insert into auth.users(id) values
  ('22222222-2222-4222-8222-222222222222'),
  ('33333333-3333-4333-8333-333333333333');
