# CloudCost Sentinel — Execution flow

This document records the actual current source flow and separates it from planned customer launch paths. File/function names below are based on the repository at Phase 1; update this record when implementation changes.

## Browser startup and screen rendering

1. `frontend/index.html` provides the browser root and Vite entry.
2. `frontend/src/main.tsx` imports global styles, mounts React `App`, and wraps it with `ErrorBoundary` and `AuthGate`.
3. `frontend/src/components/AuthGate.tsx` and `frontend/src/supabase.ts` manage the Supabase browser session when public Supabase configuration is present; demo/configuration behavior is separate.
4. `frontend/src/App.tsx` selects a hash-based workspace screen, owns dashboard state, loads API resources, and coordinates analysis, approvals, report download, and export actions.
5. `frontend/src/api.ts` builds HTTP requests to the configured backend. Authenticated requests obtain the current Supabase access token and pass it as a bearer token.
6. `frontend/src/components/*` render the dashboard, account/integration/settings screens, charts, decisions, reports, and approvals from typed API state.

## Backend startup and request path

1. `backend/main.py` constructs the FastAPI application and selects its repository at import time: production uses `SupabaseRepository`; local/development/demo use `DatabaseRepository` (SQLite).
2. The FastAPI lifespan calls `settings.validate_startup()`, initializes persistence, and in production checks `db.check_ready()` against the expected Supabase schema contract.
3. CORS middleware allows configured origins. `request_safety_limits` bounds request bodies and applies the current in-process rate limiter to public demo write endpoints.
4. A protected route depends on `require_viewer`, `require_reviewer`, or `require_admin` from `backend/auth.py`. JWT validation identifies the user; `_resolve_workspace` resolves membership through Supabase; role checks run before the route handler; the repository request scope is reset after the dependency completes.
5. `backend/main.py` handlers validate request models, call domain services/repositories, and translate known persistence/provider failures into bounded HTTP responses.

## Live cost analysis path (production target already represented in source)

1. Browser `App.tsx` calls `runAnalysis` in `frontend/src/api.ts`, which POSTs `/api/analyze` with the selected analysis input and bearer token.
2. `backend/main.py::analyze_anomaly` requires a viewer and chooses configured AWS ingestion or a permitted development/demo scenario. Production startup requires AWS Cost Explorer to be enabled; production requests use the workspace's saved role/account connection and budget configuration.
3. `backend/services/aws_cost_explorer.py::fetch_recent_costs` assumes the customer role using STS and its per-workspace external ID, checks the AWS account identity, admits the durable workspace quota, and calls Cost Explorer `GetCostAndUsage` with a bounded daily date range.
4. `backend/services/cost_analyzer.py` normalizes cost points and computes baseline, delta, persistence, budget burn, forecast, and uncertainty deterministically.
5. `backend/services/decider_client.py` evaluates the configured deterministic rules or HTTP provider. Confidence/error safeguards route uncertain outcomes to human approval. The decision provider is not an AWS action executor.
6. `backend/services/narrator.py::generate_report` optionally calls OpenRouter with bounded metric evidence and a strict JSON schema; otherwise it returns a deterministic explanation. The narrator cannot override the policy decision.
7. The report, anomaly, decision, approval, and source/data-quality metadata are persisted as a bundle. In production the caller JWT is used for Supabase PostgREST/RLS and private Storage access; SQLite is not a production fallback.
8. The API returns typed analysis results to `App.tsx`, which updates observed/simulated provenance, decision, report, and approval state.

## Reload and follow-up paths

- On app load, `App.tsx` fetches health/scenarios and, for the authenticated workspace, the latest saved analysis from `GET /api/analysis/latest`; it separately fetches decisions and approvals.
- `GET /api/decisions` and `GET /api/approvals` read the current workspace records.
- `POST /api/approvals/{approval_id}/decision` requires reviewer role and records an internal state transition; it does not call AWS to change infrastructure.
- `GET /api/reports/{report_id}/download` requires authenticated tenant access and produces a short-lived download path for a private stored report.
- `/api/integrations/aws` routes require admin role to configure, verify, or disconnect a customer-owned role. Verification invokes STS and may make a billable Cost Explorer request.
- `/api/health/live`, `/api/health`, and `/api/health/ready` provide liveness, provider status, and persistence/schema readiness without exposing credentials.

## External services and trust boundaries

| Flow | External boundary | Sensitive material / authorization |
| --- | --- | --- |
| Browser authentication | Supabase Auth | Public URL/key in browser; user session token; strict redirect allowlist and email delivery configuration. |
| Tenant database and report objects | Supabase PostgREST/Postgres RLS/Storage | User bearer token plus public anon key. No service-role key in browser or normal production request path. |
| Customer billing telemetry | AWS STS and Cost Explorer | Backend platform identity can assume constrained customer role; unique workspace external ID; customer role is read-only for billing. |
| AI narrative (optional) | OpenRouter | Backend-only API key; bounded non-identifying metric summary; no infrastructure credentials or raw account identifiers. |
| Notification delivery (conditional) | SNS/SES adapter today; future provider only after launch decision | Server-side credentials and tenant-authorized recipient selection; no mock delivery represented as real. |
| Subscription billing (conditional) | Provider API and webhook | Server-side secret; signed webhook verification, replay protection, and server-side entitlement updates. |

## Known gaps to close in later phases

- Public deployment remains a synthetic demo; the live Supabase migrations/RLS, production IAM setup, customer role connection, and browser lifecycle have not been proven against live accounts.
- Demo request limiting is process-local, not shared across instances.
- There is no subscription billing, account deletion/retention automation, invitation/member administration, or complete support workflow.
- Supabase production auth needs a configured custom SMTP sender for customer email delivery.
- Existing documentation is inconsistent in places; Phase 2 must reconcile stale descriptions with current code.
