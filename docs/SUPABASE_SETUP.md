# Supabase setup status and migration guide

The ordered SQL migration under `supabase/migrations/` defines the initial tenant-owned records, membership roles, RLS policies, private report bucket, and metadata tables. It has **not** been applied or exercised against a Supabase project. The running API still uses SQLite, and frontend Supabase Auth and tenant-aware repository calls are not implemented. Do not treat the presence of SQL as a live or production-ready integration.

## Before applying

1. Create/select a dedicated Supabase project and enable the intended Auth providers.
2. Back up any existing project and review the SQL with your database owner. Do not apply this initial schema over production data without a migration plan.
3. Apply the migration in a disposable project first and run cross-tenant RLS tests before using customer data.
4. Configure a private report bucket. The migration sets a 20 MiB limit and restricts MIME types; report generation/download lifecycle and signed download endpoints remain to be implemented.

## Expected deployment secrets when the adapter is implemented

- Frontend public values: `VITE_API_BASE_URL` only. A future Supabase browser client may use the public Supabase URL and publishable/anon key, never a service key.
- Backend: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (only if needed for user-scoped server calls), and `SUPABASE_SERVICE_ROLE_KEY` only if a reviewed backend operation truly requires elevated access. The service key must remain server-only.
- Backend AI is optional: `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` together. Choose a model shown as available by OpenRouter at deployment time; no model is hard-coded as free or guaranteed available.

Do not add Supabase or OpenRouter secrets to Vercel frontend variables with a `VITE_` prefix. Store backend secrets in Render's private environment settings. Never paste secret values into chat or commit them.

## Known migration limitations

This is a schema foundation, not a completed persistence release. Authenticated application roles, repository adapter, schema migration runner, project-backed RLS/storage tests, report file lifecycle, data export/deletion, and tenant-isolation tests are still required. The present API does not issue organization IDs or use these policies.
