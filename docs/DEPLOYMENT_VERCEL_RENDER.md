# Vercel + Render deployment

This repository's public demo is synthetic and shared. It uses mock Decider and report providers, SQLite, and application-only approval records. The current Render configuration uses ephemeral `/tmp` storage unless a writable persistent disk is verified and explicitly configured. It never applies changes to AWS. Do not configure AWS Cost Explorer or real notification providers for this demo.

No additional third-party API was introduced by this repair. The default demo uses local simulated providers and requires no provider API key. Optional live AWS features are outside the free default: Bedrock inference is billed by model usage, AWS Cost Explorer charges $0.01 per API request, and SNS may charge for messages/delivery. Keep the demo provider settings below to avoid those API charges. See [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), [Cost Explorer API pricing](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/), and [SNS pricing](https://aws.amazon.com/sns/pricing/).

## Live connectivity findings (2026-10-26)

- The stable frontend URL `https://cloudcostsentinel.vercel.app` returned HTTP 200 and served the CloudCost Sentinel HTML publicly.
- Render liveness, health, and readiness returned HTTP 200. Health reported `environment=demo`, `auth.mode=explicit_demo`, simulated Decider and Bedrock providers, and disabled AWS Cost Explorer. Readiness separately reported its database as connected.
- Render accepted CORS preflight from the configured Vercel project URL `https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app`, but returned HTTP 400 for the stable production alias `https://cloudcostsentinel.vercel.app`. Add both exact origins to Render's `CORS_ORIGINS` as shown below, then redeploy/restart the service.
- Render/Vercel dashboard settings, deployed commit SHAs, and provider logs are not accessible from this workspace. The live frontend currently serves HTML, but its deployment SHA and build-time API URL cannot be verified here.

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
CORS_ORIGINS=https://cloudcostsentinel.vercel.app,https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app
```

Do not configure `ALLOW_MOCK_IN_PRODUCTION`; it is not read by this application. Production startup already rejects mock providers.

If users access another stable Vercel alias, append that exact origin, comma-separated, without a trailing slash. Do not use `*`. Keep Render's injected `PORT`; do not set `DATABASE_URL` because PostgreSQL is not implemented. `/tmp/cloudcost-sentinel.db` is ephemeral and records can disappear on restart/redeploy. To preserve state, attach and verify a writable persistent disk first, then set `DATABASE_PATH` to its mount; a configured unwritable path causes a clear startup failure, never a fallback. [Render provides `RENDER=true`](https://render.com/docs/environment-variables); current startup validation refuses `ENVIRONMENT=development` on Render and requires `HOST=0.0.0.0`.

Do not copy these demo settings into a real production deployment. Production requires validated OIDC/JWKS, non-mock providers, and persistent storage; the browser OIDC sign-in flow is not implemented.

## Post-deploy smoke checks

First verify that `GET /api/health` says `environment=demo`, auth mode `explicit_demo`, and mock providers `simulated`; `GET /api/health/ready` must be a separate response with HTTP 200 and database `connected`.

Check the exact-origin preflight:

```sh
curl -i -X OPTIONS https://cloudcostsentinel.onrender.com/api/demo/scenarios \
  -H 'Origin: https://cloudcostsentinel.vercel.app' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

It should return HTTP 200 and `Access-Control-Allow-Origin` matching the requesting origin. Repeat for analysis:

```sh
curl -i -X OPTIONS https://cloudcostsentinel.onrender.com/api/analyze \
  -H 'Origin: https://cloudcostsentinel.vercel.app' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Then verify `GET /api/demo/scenarios`, `GET /api/approvals`, `GET /api/decisions?limit=15`, and a synthetic `POST /api/analyze` with `{"scenario_id":"compute_spike","use_aws_cost_explorer":false}` from the Vercel page. A request from an unlisted origin must not receive `Access-Control-Allow-Origin`. Confirm browser analysis and approvals render and that re-submitting a reviewed approval returns HTTP 409. These checks are still required after correcting service configuration; a direct health 200 alone does not verify the browser path.

## Verification status

GitHub Actions [run 40354434812](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/runs/40354434812) passed both backend and frontend jobs for the repair. The backend suite passed 44 tests, the pattern suite passed 5 tests, and frontend API tests passed 15 tests in local clean-dependency runs. The two backend test defects were a Render configuration fixture missing required `HOST=0.0.0.0` and a missing `cost_explorer` test import. The stable Vercel alias still needs to be added to Render's allowlist; rerun the live CORS check after changing `CORS_ORIGINS`.
