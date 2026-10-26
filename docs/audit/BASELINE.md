# CloudCost Sentinel audit baseline

Audit date: 2026-10-26. Checkout: `main` at `f2a3821` before this turn; working tree was clean and tracked `origin/main`.

## Architecture confirmed

- React 19, TypeScript and Vite frontend in `frontend/`; FastAPI API in `backend/`.
- Backend API repository is SQLite (`backend/database/db.py`). `DATABASE_URL` is rejected. Render demo uses `/tmp/cloudcost-sentinel.db` unless configured otherwise, so hosted records are ephemeral.
- Authentication is generic OIDC bearer validation. The explicit public demo intentionally allows unauthenticated access and uses shared demo records. There is no user/org ownership in API queries.
- Decision provider supports the existing deterministic mock and HTTP Strands Decider. AWS Cost Explorer remains an independent optional read-only source.
- The prior narrative path invoked Strands Agents with Amazon Bedrock. No OpenRouter client existed at baseline.
- No Supabase project config/migrations or Postgres repository adapter existed at baseline. No browser Supabase Auth flow existed.

## Deployment observations

- `https://cloudcostsentinel.onrender.com/api/health` returned HTTP 200 and identified the service as `environment=demo`, `auth.enabled=false`, simulated decision/narrative providers, and Cost Explorer disabled.
- `/api/health/ready` returned HTTP 200 with the SQLite database reachable. This is not evidence of durable storage.
- `https://cloudcostsentinel.vercel.app/` returned HTTP 200 and the expected product title.
- `https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app/` returned a Vercel login/access-protection page in the audit, so that alias was not visually inspectable.
- `https://cloudsentinel-ai.vercel.app/` returned a minimal page titled `frontend`; repository ownership/relationship could not be verified from the reachable response. Do not treat it as an official alias without account-side evidence.
- No connected Vercel, Render, or Supabase dashboard was available to inspect deployed branch/build settings or secrets.

## Confirmed issues and severity

| Severity | Finding | Evidence / location | Status |
|---|---|---|---|
| Critical | Production data path was SQLite-only; no organization scoping or durable Supabase persistence. | `backend/database/db.py`, `backend/config.py`, `backend/main.py` | Migration foundation added in this change; repository/API still need implementation before production use. |
| Critical | Protected production auth was generic OIDC, not Supabase Auth; no browser login/session flow or tenant authorization. | `backend/auth.py`, `frontend/src/` | Not fixed in this change. |
| High | AI narrative was coupled to Amazon Bedrock. | `backend/services/strands_agent.py`, `backend/config.py` | Replaced with optional backend-only OpenRouter client; verification in `VERIFICATION.md`. |
| High | Shared unauthenticated demo allows shared synthetic records and approval state. | `backend/config.py`, `backend/main.py` | Remains intentional for `ENVIRONMENT=demo`; not suitable for private customer data. |
| Medium | A report with no configured external AI provider was deterministic, but UI/provider metadata described the backend as Bedrock-specific. | API health and frontend types/components | Health uses `narrator` and explicitly reports offline/OpenRouter states. |
| Medium | Frontend is a single dashboard, with no account, workspace, scan-history, or findings routes. | `frontend/src/App.tsx` | Not rebuilt in this change. |

## Baseline checks

- Python backend baseline: `tests/test_backend.py` — 44 passed (Python 3.11.9).
- Frontend baseline: `npm ci`, 20 tests, lint and production build were started; `npm ci`, 20 tests, and lint passed. The running build session ended before its result could be recovered; see verification caveat.
- `npx-skill` and Supabase CLI were not installed on the audit machine.
- The repository was on the user-requested single branch `main`; no branch was created.
