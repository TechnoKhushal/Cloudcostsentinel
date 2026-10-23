# Vercel + Render deployment

This repository's public demo is synthetic and shared. It uses mock Decider and report providers, SQLite, and application-only approval records. The current Render configuration uses ephemeral `/tmp` storage unless a writable persistent disk is verified and explicitly configured. It never applies changes to AWS. Do not configure AWS Cost Explorer or real notification providers for this demo.

## Confirmed connectivity findings (2026-10-24)

- A live `GET /api/health` returned HTTP 200, but reported `environment=development`, `auth.enabled=false`, and `mode=development_bypass`. A live `GET /api/health/ready` returned the same health-shaped payload. That does not match this repository's readiness handler, which returns a separate `status=ready|not_ready` response after checking SQLite. The hosted backend therefore appeared to be serving an older build or configuration. The latest Render import log also reported `ModuleNotFoundError: No module named 'strands_decider'`; this repair removes that API startup dependency. Render's configured branch, commit, root directory, and build command cannot be verified without dashboard access.
- An `OPTIONS /api/demo/scenarios` request with the deployed Vercel origin returned HTTP 400 and `Disallowed CORS origin`. This confirms the backend's effective CORS allowlist does not include that origin.
- In a browser without a Vercel session, the supplied Vercel URL redirected to Vercel login. The application UI and its Network/Console failures could not be inspected without access to the deployment.
- Later direct probes intermittently failed DNS resolution. Check results again after deployment; the intermittent failures do not establish that either service is down.

## Vercel frontend settings

Use the Vercel project for the frontend with Root Directory `frontend`, Install Command `npm ci`, Build Command `npm run build`, and Output Directory `dist`.

Set this non-secret build variable in each environment that should serve the app, then redeploy:

```text
VITE_API_BASE_URL=https://cloudcostsentinel.onrender.com
```

Use the backend origin only: no `/api` suffix and no trailing slash. The frontend adds API paths itself. This is the only API configuration variable the current frontend needs. Never put AWS credentials, OIDC client secrets, or backend tokens in a `VITE_*` variable; Vite embeds those values in public browser assets.

If the app is intended to be public, review Vercel Deployment Protection for the production domain and choose the appropriate access policy in the Vercel project. The observed login redirect prevented browser verification; do not assume it is a CORS symptom.

## Render backend settings for the simulated demo

Use repository root directory and branch `codex/repair-vercel-render-connectivity` until the repair is merged. There is no checked-in `render.yaml`, so verify these settings in the Render dashboard. For a Docker deployment, use the repository Dockerfile. For a native Python service, use Python 3.11 (the repository `.python-version` pins Render to the same runtime as CI and Docker), set the build command to `pip install -r requirements.txt`, and use this start command:

```text
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Set these non-secret runtime variables in Render:

```text
ENVIRONMENT=demo
AUTH_ENABLED=false
DECIDER_PROVIDER=mock
BEDROCK_PROVIDER=mock
AWS_COST_EXPLORER_ENABLED=false
NOTIFICATION_PROVIDER=disabled
ENABLE_TEST_FIXTURE_ENDPOINT=false
HOST=0.0.0.0
DATABASE_PATH=/tmp/cloudcost-sentinel.db
CORS_ORIGINS=https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app
```

Do not configure `ALLOW_MOCK_IN_PRODUCTION`; it is not read by this application. Production startup already rejects mock providers.

If users access another stable Vercel alias, append that exact origin, comma-separated, without a trailing slash. Do not use `*`. Keep Render's injected `PORT`; do not set `DATABASE_URL` because PostgreSQL is not implemented. `/tmp/cloudcost-sentinel.db` is ephemeral and records can disappear on restart/redeploy. To preserve state, attach and verify a writable persistent disk first, then set `DATABASE_PATH` to its mount; a configured unwritable path causes a clear startup failure, never a fallback. [Render provides `RENDER=true`](https://render.com/docs/environment-variables); current startup validation refuses `ENVIRONMENT=development` on Render and requires `HOST=0.0.0.0`.

Do not copy these demo settings into a real production deployment. Production requires validated OIDC/JWKS, non-mock providers, and persistent storage; the browser OIDC sign-in flow is not implemented.

## Post-deploy smoke checks

First verify that `GET /api/health` says `environment=demo`, auth mode `explicit_demo`, and mock providers `simulated`; `GET /api/health/ready` must be a separate response with HTTP 200 and database `connected`.

Check the exact-origin preflight:

```sh
curl -i -X OPTIONS https://cloudcostsentinel.onrender.com/api/demo/scenarios \
  -H 'Origin: https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

It should return HTTP 200 and `Access-Control-Allow-Origin` matching the requesting origin. Repeat for analysis:

```sh
curl -i -X OPTIONS https://cloudcostsentinel.onrender.com/api/analyze \
  -H 'Origin: https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Then verify `GET /api/demo/scenarios`, `GET /api/approvals`, `GET /api/decisions?limit=15`, and a synthetic `POST /api/analyze` with `{"scenario_id":"compute_spike","use_aws_cost_explorer":false}` from the Vercel page. A request from an unlisted origin must not receive `Access-Control-Allow-Origin`. Confirm browser analysis and approvals render and that re-submitting a reviewed approval returns HTTP 409. These checks are still required after correcting service configuration; a direct health 200 alone does not verify the browser path.

## CI status

GitHub Actions run [#5 for commit `52c65e5`](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40003922854) had a successful frontend job and successful backend dependency installation and Python compilation. `Run Backend Tests` failed; pattern tests and the standalone demo were skipped. The public check annotation only contains `Process completed with exit code 1`. Downloading job logs requires repository admin rights, and the GitHub CLI was unavailable in the inspection environment, so the failing assertion/traceback could not be confirmed here. Do not treat a speculative local dependency error as the CI root cause; obtain the full job log before changing backend tests or dependencies.
