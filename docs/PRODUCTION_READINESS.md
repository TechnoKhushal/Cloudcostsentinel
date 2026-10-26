# Production readiness and deployment configuration

Audit date: 2026-10-26
Current source revision audited: `43df07d23ea2c5262d34079926454d2db59b78c2` before audit documentation changes.

## Verdict

**Public synthetic demo: operational in the checks below. Authenticated production: NOT READY.** The browser-visible site and API currently operate in explicitly simulated demo mode. Do not present this as live AWS telemetry or an authenticated, tenant-isolated production service.

## Repository and deployed state

- Local checkout and fetched `origin/main` matched at the audited starting revision. The only remote branch is `main`.
- Vercel and Render dashboard credentials are not connected to this workspace. The Vercel and Render deployed commit IDs, Render service root/branch settings, and Vercel project settings cannot be verified from public health endpoints. The HTTP responses show application state, not a trustworthy source revision.
- The repository has no `render.yaml`; Render configuration is dashboard-managed. Set its branch to `main`, root directory to repository root, and start command to `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` (or use the checked-in Dockerfile).
- Vercel should use root `frontend`, install `npm ci`, build `npm run build`, output `dist`, and deploy the production branch `main`.
- `frontend/vercel.json` sets security headers including a CSP allowing same-origin scripts/assets and the Render API origin. Any change to `VITE_API_BASE_URL` must be reflected in the CSP `connect-src` directive, then redeployed and checked in a browser.

## Exact environment configuration for the current free demo

### Vercel

Set this public build-time variable for each Vercel environment (Production and Preview only if those previews should call the public demo API), then redeploy:

```text
VITE_API_BASE_URL=https://cloudcostsentinel.onrender.com
```

This is the only frontend API variable. Do not add `/api`, credentials, AWS keys, or other secrets to a `VITE_*` value.

### Render

For a safe, synthetic-only demo, explicitly set:

```text
ENVIRONMENT=demo
HOST=0.0.0.0
AUTH_ENABLED=false
DECIDER_PROVIDER=mock
AWS_COST_EXPLORER_ENABLED=false
NOTIFICATION_PROVIDER=disabled
ENABLE_TEST_FIXTURE_ENDPOINT=false
DATABASE_PATH=/tmp/cloudcost-sentinel.db
CORS_ORIGINS=https://cloudcostsentinel.vercel.app,https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app
```

`PORT` and `RENDER` are supplied by Render; do not set them manually. Include only exact frontend origins that users actually access. Current stable-origin preflight was verified; dashboard configuration and the generated alias's current necessity were not independently inspected. Do not use wildcard CORS.

No AWS, OpenRouter, Strands Decider, email, or notification API key is needed for this configuration. The demo uses local simulated providers. `/tmp` is ephemeral, so approvals/history can disappear when Render restarts or redeploys. Supabase schema foundations exist but are not wired to the API.

## Live checks performed

| Check | Result |
| --- | --- |
| `GET https://cloudcostsentinel.onrender.com/api/health/live` | HTTP 200, `{"status":"ok"}` |
| `GET https://cloudcostsentinel.onrender.com/api/health/ready` | Historical response: HTTP 200; `ready`, environment `demo`, database `connected`, simulated providers. Current code reports narrative state as `offline` when OpenRouter is unset. |
| `GET https://cloudcostsentinel.onrender.com/api/demo/scenarios` | HTTP 200, synthetic scenario list |
| `OPTIONS /api/demo/scenarios` from `https://cloudcostsentinel.vercel.app` | HTTP 200; `Access-Control-Allow-Origin` exactly matched the requested origin; `authorization,content-type` allowed |
| `GET https://cloudcostsentinel.vercel.app/` | HTTP 200, public dashboard title |
| Vercel Content Security Policy | Present; `connect-src` allows same-origin and `https://cloudcostsentinel.onrender.com` |
| Browser dashboard | Rendered; API connected; demo and synthetic labels shown; scenario options and existing analysis/review history visible; no warnings/errors returned by the browser console capture |

The shared demo already contained analyzed scenarios and reviewed approval items. No approval was approved/rejected during this audit, to avoid changing shared public demo state. Browser verification therefore confirms the current page and data reads, not a fresh approval transition. Locally, approval conflict and provider behavior are covered by backend tests.

## Local clean verification

Environment: Windows, Python 3.11.9, Node 24.21.0, npm 11.19.0. A fresh Python environment was created under ignored `.tmp/`; frontend used `npm ci`.

- Backend: `python -m compileall -q backend patterns scripts tests` passed; `pytest -vv tests/test_backend.py` passed 44/44; `pytest -vv patterns/threshold_aware_anomaly_response/test_pattern.py` passed 5/5; standalone pattern example exited 0 and reported `mock-simulated` output. Dependency audit initially flagged `mcp==2.1.1` (`CVE-2026-59951`) and bootstrap `setuptools==65.5.0` (multiple advisories). `requirements.txt` now constrains MCP to `>=1.30.0,<2.0.0` and setuptools to `>=84.1.0`; both `pip-audit -r requirements.txt` and `pip-audit --local` now report no known vulnerabilities.
- Frontend: `npm ci` succeeded; npm reported 0 vulnerabilities; `npm test` passed 20/20; `npm run lint` passed; `npm run build` passed. Vite emitted a non-failing large-chunk advisory (626.29 kB minified; 186.67 kB gzip).
- CI at audited starting revision: [run 40364128369](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40364128369) completed successfully.
- CI at the dependency and CSP hardening revision `f8d806540dda7874fa0793f21f5a2734ce1c0073`: [run 40367402354](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40367402354) completed successfully, including Python dependency audit.
- Docker CLI is installed, but the local Docker Desktop Linux engine was stopped, so Docker image build/health verification could not run.
- Browser check: the production page showed API connected, simulated/demo badges, populated scenario analysis, report and decision, and existing approval history. Approval status/search controls returned filtered records and restored the default Pending view; no browser console errors or warnings were returned. No review transition was submitted to the shared public queue.
- Earlier CI failures: public metadata for runs [40003922854](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40003922854), [40019931421](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40019931421), [40020275888](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40020275888), and [40020470191](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40020470191) shows failed check steps and generic exit-code annotations. GitHub returned HTTP 403 (`Must have admin rights to Repository`) for raw-log requests to each run, so their exact assertions/tracebacks cannot be confirmed.

## Blockers before authenticated production

1. Implement and test the frontend OIDC authorization-code + PKCE login/callback/token lifecycle; the frontend currently does not authenticate users.
2. Attach and verify durable storage, migration/backup/restore behavior, and operational recovery. Current public demo uses ephemeral SQLite unless Render is explicitly configured with a writable disk.
3. Configure and verify real providers, IAM least privilege, provider timeouts/error states, and live data freshness. Current Render responses explicitly report simulated providers and AWS Cost Explorer off.
4. Add shared rate limiting or keep one backend process; current demo controls are process-local and public.
5. Obtain dashboard access or inspect Vercel/Render deployment details to record the actual deployed SHAs, branch, root, build/start settings, environment scopes, and production access policy.
6. Run an isolated end-to-end test deployment for a fresh analysis, approval success, duplicate/concurrent 409, and API failure/retry. Do not use the shared public demo approval queue for destructive or state-changing QA.

Until these gates are met, the verdict remains **NOT READY for authenticated production**. The public synthetic demo status should not be confused with production readiness.
