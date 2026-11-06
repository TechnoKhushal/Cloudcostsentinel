# Verification log

## Production schema, PKCE, and deployment follow-up (2026-11-07)

- Applied all four ordered migrations in a disposable PostgreSQL 16 container after creating minimal Supabase-shaped `auth` and `storage` schemas. The first run caught and fixed a missing `UNIQUE (organization_id, id)` target needed by composite foreign keys from findings/reports to scans. This is a local compatibility smoke test; the hosted Supabase migration/RLS/Storage implementation remains unverified.
- Smoke-tested personal workspace provisioning and owner-role lookup, `persist_analysis_bundle`, cross-user read denial for an unassociated user, AWS quota rejection and saturation, and workspace budget update triggers. Hosted Supabase still needs adversarial RLS and Auth tests.
- Set Supabase Auth to explicit PKCE, and added a frontend unit test for PKCE, session restoration, and refresh options.
- Backend tests: 58 passed. Frontend tests: 23 passed; lint and production build passed. GitHub Actions succeeded for [commit 6585ac4](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/42288761801).
- GitHub Actions succeeded for [commit 9381c4f](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/42289972839), including the new PostgreSQL 16 migration, workspace persistence, quota, and tenant read-isolation smoke step.
- Live recheck: Render health/readiness and Vercel root returned HTTP 200; Vercel served the updated UI bundle. Render continues to report `environment=demo`, SQLite persistence, simulated decisions, and disabled AWS ingestion. CORS from Vercel origin to Render API returned the matching allowed origin.
- Production deployment is still blocked on real Supabase project config/migration application, production Vercel/Render variables, and a least-privilege platform AWS role. No production-mode switch or real customer AWS call was performed.

## Supabase integration code update (2026-10-27)

This update adds a production-only Supabase Auth/JWT, user-token PostgREST and private Storage code path, report download endpoint, profile endpoint, and three ordered migrations. The original migration files are unchanged; migration 003 adds the membership role and owner cleanup policy. It also adds a Supabase sign-up/sign-in/recovery gate, Vercel public Supabase configuration, and lazy chart loading. Production startup requires Supabase, authenticated requests, deterministic non-mock decisions and non-mock notifications. Shared AWS Cost Explorer credentials are rejected until per-organization cloud credentials exist.

### Local checks

| Command | Result |
|---|---|
| `.tmp/audit-venv/Scripts/python.exe -m compileall -q backend patterns scripts tests` | Passed. |
| `.tmp/audit-venv/Scripts/python.exe -m pytest -q tests` | 52 passed, including mocked Supabase repository and static migration-structure tests. No real Postgres or RLS behavior is proven. |
| `.tmp/audit-venv/Scripts/python.exe -m pytest -q patterns/threshold_aware_anomaly_response/test_pattern.py` | 5 passed. |
| `.tmp/audit-venv/Scripts/python.exe -m pip_audit` | No known vulnerabilities found. |
| `frontend: npm test` | 20 passed. |
| `frontend: npm run lint` | Passed. |
| `frontend: npm run build` | Passed. Main JS 283.89 kB; lazy chart JS 359.27 kB. No 500 kB chunk warning. |
| `git diff --check` | Passed. |

### Live checks and limits

- Render `/api/health/live`, `/api/health`, and `/api/health/ready` returned HTTP 200. The returned environment is still `demo`, with simulated decisions, offline narrator, and demo database state.
- Vercel `/` returned HTTP 200 and HTML referencing the previously deployed bundle. This does not establish that the new frontend is deployed.
- The only local and remote branch is `main`; no Supabase/Render/Vercel dashboard credentials were available. The new migrations were not applied, and deployment revisions/configuration were not verified.
- Authentication lifecycle, RLS isolation, SQL execution, private Storage authorization, report deletion/retention, multi-user browser flows, organization invitations, production rate limits, per-organization cloud accounts, complete frontend product workflows, and live API persistence remain unverified or unimplemented.
- Pushing code does not make the public service production-ready. Keep the demo/production distinction visible until the project-backed checks and deployment setup are complete.

Audit/change date: 2026-10-26. All commands below were run locally; they do not prove Render/Vercel deployment or a Supabase project migration.

## Baseline (before edits)

| Command / check | Result |
|---|---|
| `git status --short --branch`, `git log -1 --oneline` | Clean `main...origin/main`, HEAD `f2a3821`. |
| `.tmp/audit-venv/Scripts/python.exe -m pytest -q tests/test_backend.py` | 44 passed in 6.16s. |
| Frontend `npm ci` | Passed; npm reported 0 vulnerabilities. |
| Frontend `npm test` | 20 tests passed. |
| Frontend `npm run lint` | Passed. |
| Frontend build | Started; result was not recovered from the completed terminal session. |
| `pip-audit` | No known vulnerabilities found (per command output). |
| Public deployment GET health/readiness and Vercel root | HTTP 200 on the accessible URLs; see `BASELINE.md`. |

## After edits

| Command / check | Result |
|---|---|
| `python -m compileall -q backend tests` | Passed. |
| `.tmp/audit-venv/Scripts/python.exe -m pytest -q tests/test_backend.py` | 44 passed in 6.16s after the provider/config/API health changes. |
| `.tmp/audit-venv/Scripts/python.exe -m pytest -q tests` | 46 passed in 7.56s, including mocked OpenRouter success and 429 fallback. |
| `.tmp/audit-venv/Scripts/python.exe -m pytest -q patterns/threshold_aware_anomaly_response` | 5 passed in 12.12s. |
| `.tmp/audit-venv/Scripts/python.exe -m pip_audit` | No known vulnerabilities found. |
| `frontend/npm test` | 20 passed. |
| `frontend/npm run lint` | Passed. |
| `frontend/npm run build` | Passed; Vite reports the existing JavaScript bundle at 626.33 kB, above its 500 kB advisory threshold. |
| `git diff --check` | Passed; Git printed line-ending normalization warnings for three existing CRLF-tracked files. |
| Supabase SQL migration | Not applied: no project credentials/CLI and no local Supabase runtime available. SQL policy behavior is unverified. |
| Supabase persistence, Auth and cross-tenant API isolation | Not implemented/verified. |
| Browser E2E and responsive visual QA | Not run in this pass. |
| Vercel/Render redeploy | Not triggered; no dashboard deployment controls available. |

## Post-push live recheck

Commit `26a792e397755e99c6aec901acdc7ef2f4df1285` was pushed to `origin/main`. About one minute later, Render `/api/health` and `/api/health/ready` still returned HTTP 200 with the old `providers.bedrock` response shape. Vercel root returned HTTP 200 and the expected title, but that alone does not establish which frontend revision is serving. The code push succeeded; deployment of the new source was not observed during this check. No Vercel or Render dashboard/log access was available to inspect deployment status.

## Limits

OpenRouter uses one retry for 429/5xx-class responses, a 20-second request timeout, a 900-token output budget, and schema validation. The code does not yet persist AI usage events, enforce per-tenant quotas, or provide a circuit breaker. The offline report is labeled deterministic fallback. No real paid model invocation was made.
