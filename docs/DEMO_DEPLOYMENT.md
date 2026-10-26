# Public simulated demo deployment

This mode is an opt-in, shared demonstration using synthetic scenarios, simulated decision/report providers, and SQLite. It does not require AWS credentials or an identity provider. Approval actions update only the shared demo review record; they never execute AWS changes. Limits are per backend process, so a horizontally scaled deployment needs a shared rate limiter before public exposure.

## Render backend

Use the repository root (not `backend/`) and branch `main`. The only remote branch currently published is `main`. The repository does not contain a `render.yaml`; confirm the Render service dashboard points to `main` and the repository root because dashboard settings are not available from this workspace. Use the repository Dockerfile, or configure the native Python service with Python 3.11 (the checked-in `.python-version` matches CI and Docker) and build command `pip install -r requirements.txt`. The API does not import or require the standalone model-serving package; to run a separate local model server, install `requirements-decider-model.txt` in that server's environment. Set the start command to:

```sh
uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
```

Set these Render environment variables:

```text
ENVIRONMENT=demo
AUTH_ENABLED=false
DECIDER_PROVIDER=mock
AWS_COST_EXPLORER_ENABLED=false
NOTIFICATION_PROVIDER=disabled
ENABLE_TEST_FIXTURE_ENDPOINT=false
HOST=0.0.0.0
DATABASE_PATH=/tmp/cloudcost-sentinel.db
CORS_ORIGINS=https://cloudcostsentinel.vercel.app,https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app
```

Do not add `ALLOW_MOCK_IN_PRODUCTION`; the application does not read that legacy variable. Production startup already rejects mock providers.

The current Render demo has no verified persistent disk, so use `/tmp/cloudcost-sentinel.db`. This is writable demo storage, not durable: approvals and other records may disappear on restart/redeploy. Do not configure `DATABASE_URL`: PostgreSQL is not implemented and startup rejects it. Supabase migration foundations are documented in `SUPABASE_SETUP.md`, but are not yet used by the API.

## Vercel frontend

Set Root Directory `frontend`, Install Command `npm ci`, Build Command `npm run build`, Output Directory `dist`, and set `VITE_API_BASE_URL=https://cloudcostsentinel.onrender.com` in the intended deployment environment. The value is the backend origin only, is public, and is embedded at build time. Redeploy after changing it. The backend CORS list must include the exact deployed frontend origin and any intentionally supported stable production alias; do not add wildcard origins.

## Verify after deployment

```sh
curl -i https://cloudcostsentinel.onrender.com/api/health/live
curl -i https://cloudcostsentinel.onrender.com/api/health/ready
curl -i https://cloudcostsentinel.onrender.com/api/health
curl -i https://cloudcostsentinel.onrender.com/api/demo/scenarios
```

For automated checks, run:

```sh
python scripts/smoke_test_deployment.py https://cloudcostsentinel.onrender.com \
  --frontend-origin https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app
```

The live probe should return 200. In `ENVIRONMENT=demo`, readiness should return 200 with database `connected` and providers `simulated`. Confirm browser analysis responses label the anomaly, Decider provider, and report as simulated. The current `/tmp` database can lose records on restart/redeploy. A public demo shares approval state between visitors and is not an authenticated tenant environment.

## Authenticated production

Production remains separate from this demo. Supabase Auth, tenant-scoped repository integration, RLS verification and a browser sign-in flow are not implemented yet, so this repository is not ready for private customer data.
