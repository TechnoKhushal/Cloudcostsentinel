# Supabase Auth, persistence, and private reports

The API now has a production code path that validates Supabase Auth JWTs, provisions a personal workspace on first authenticated API use, and performs PostgREST/Storage calls using only that caller's JWT and the public anon key. PostgreSQL RLS remains the authorization boundary. The repository does not contain a service-role key or direct database password.

**The migrations below have not been applied to a live Supabase project.** Unit tests use mocked HTTP and do not prove Postgres SQL syntax, RLS behavior, JWT signing-key compatibility, or Storage policies. Authenticated production is not ready until the steps under “Before production” are completed in an isolated project and the deployment is configured.

## Clean installation

1. Create a dedicated Supabase project. Enable email/password authentication and email verification. Configure allowed redirect URLs to the exact Vercel site and local development URL.
2. Set an asymmetric Supabase JWT signing key (RS256 or ES256) and note the project's URL and publishable/anon key. The backend verifies asymmetric JWTs using the Supabase JWKS endpoint.
3. Back up the project if it contains data. Apply `supabase/migrations/202610260001_initial_tenant_schema.sql`, `supabase/migrations/202610260002_api_runtime.sql`, and `supabase/migrations/202610260003_membership_role_and_storage_cleanup.sql` in order, using the Supabase SQL editor or CLI. Keep each applied migration recorded; never edit an already applied migration in place.
4. Inspect the created tables, functions, RLS policies, private `sentinel-reports` bucket, file size limit and MIME allowlist. Run adversarial tests with two isolated accounts and verify cross-workspace reads, writes, approvals, object downloads and deletes fail.
5. Configure the frontend and backend variables below. Deploy API and frontend only after migration and account-flow checks pass.

## Environment variables

### Vercel frontend

| Variable | Required | Value |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Yes | Render API origin, e.g. `https://cloudcostsentinel.onrender.com`; no `/api` suffix. |
| `VITE_SUPABASE_URL` | Yes for authenticated production | Supabase project origin, e.g. `https://<project-ref>.supabase.co`. |
| `VITE_SUPABASE_ANON_KEY` | Yes for authenticated production | Supabase publishable/anon key only. Never use a service-role key. |

### Render backend

| Variable | Required | Value |
| --- | --- | --- |
| `ENVIRONMENT` | Yes | `production`. |
| `HOST` | Yes | `0.0.0.0`. |
| `AUTH_ENABLED` | Yes | `true`. |
| `CORS_ORIGINS` | Yes | Exact comma-separated Vercel origin(s), HTTPS, no wildcard or path. |
| `SUPABASE_URL` | Yes | Same Supabase project origin as frontend. |
| `SUPABASE_ANON_KEY` | Yes | Same public key as frontend; backend sends it with each user's verified bearer token. |
| `DECIDER_PROVIDER` | Yes | `rules` for deterministic policy decisions. `mock` is blocked in production. |
| `NOTIFICATION_PROVIDER` | Yes | `disabled` until a real, separately reviewed notification integration is configured. `mock` is blocked in production. |
| `OPENROUTER_API_KEY` | No | Optional backend-only key. Omit to use the deterministic explanation. |
| `OPENROUTER_MODEL` | No | Required only with the key. Must be `openrouter/free` or an explicitly free model ID ending in `:free`; no paid fallback is allowed. Free availability, caps and pricing can change. |
| `AWS_COST_EXPLORER_ENABLED` | Yes | `false` for now. Production startup rejects `true` because one set of server AWS credentials would cross tenant boundaries. Per-organization AWS role connections are not implemented. |

`AUTH_ISSUER`, `AUTH_AUDIENCE`, and `AUTH_JWKS_URL` may be omitted for Supabase; the API derives them from `SUPABASE_URL` and uses audience `authenticated`. `PORT` is provided by Render. Do not set `DATABASE_PATH`, `DATABASE_URL`, service-role keys, AWS credentials, or secrets with a `VITE_` prefix for production.

## Upgrade, recovery, and retention

- Apply migrations in order and retain the migration history in source control. Use a disposable project to rehearse upgrades and rollback/recovery before production.
- Back up the Supabase database using the project's supported backup/export method before migrations. Restore to a separate project and verify row counts and report objects before promoting it.
- The app has no SQLite-to-Supabase import utility. Existing SQLite records are not migrated automatically; preserve and explicitly reconcile them before switching any users.
- Reports are JSON files in a private bucket at `<organization UUID>/<report ID>.json`. The API uploads before its transactionally persisted metadata bundle; on a failed database write it attempts object deletion. Downloads require an organization-filtered metadata lookup and use a short-lived signed URL. A periodic orphan/retention cleanup job, user deletion workflow, malware scanning, invitations, organization management and general-purpose uploads are not implemented.
- Audit events for the current analysis persistence RPC are append-only for ordinary authenticated users. Broader membership, account, deletion and export auditing still needs implementation.

## Before production

Run actual database and browser tests against a dedicated Supabase project: migration apply/upgrade, two-user RLS isolation, role escalation attempts, email verification, password recovery, JWT verification, profile updates, transaction rollback, concurrent approval review, private object access and cleanup. Also verify Render's deployed revision and environment, Vercel's build configuration, CORS and the end-to-end flows. No Supabase, Render or Vercel dashboard credentials were available for this change, so none of those live actions are claimed as complete.
