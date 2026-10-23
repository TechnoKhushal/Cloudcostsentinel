# Public simulated demo deployment

This mode is an opt-in, shared demonstration using synthetic scenarios, simulated decision/report providers, and SQLite. It does not require AWS credentials or an identity provider. Approval actions update only the shared demo review record; they never execute AWS changes. Limits are per backend process, so a horizontally scaled deployment needs a shared rate limiter before public exposure.

## Render backend

Use the repository root and the Dockerfile. The checked-in `.python-version` pins the native Render runtime to Python 3.11, matching CI and Docker. For a native Python service, set the build command to:

```sh
pip install -r requirements.txt && pip install --no-deps "strands-decider==0.2.0"
```

The second install provides the API wire schema without the optional local model runtime and its heavyweight dependencies. To run a separate local model server, install `requirements-decider-model.txt` in that server's environment. Set the start command to:

```sh
uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
```

Set these Render environment variables:

```text
ENVIRONMENT=demo
AUTH_ENABLED=false
DECIDER_PROVIDER=mock
BEDROCK_PROVIDER=mock
AWS_COST_EXPLORER_ENABLED=false
NOTIFICATION_PROVIDER=disabled
ENABLE_TEST_FIXTURE_ENDPOINT=false
HOST=0.0.0.0
DATABASE_PATH=/var/data/sentinel.db
CORS_ORIGINS=https://cloudcostsentinel-gaalb94rn-technokhushals-projects.vercel.app
```

Do not add `ALLOW_MOCK_IN_PRODUCTION`; the application does not read that legacy variable. Production startup already rejects mock providers.

Attach a persistent disk mounted at `/var/data`; without it, SQLite data is disposable on redeploy/restart. Do not configure `DATABASE_URL`: the current repository does not implement PostgreSQL and refuses to start in any environment when that unused variable is set. This demo uses synthetic scenario IDs only; the API rejects custom anomaly payloads and Cost Explorer requests.

## Vercel frontend

Set Root Directory `frontend`, Install Command `npm ci`, Build Command `npm run build`, Output Directory `dist`, and set `VITE_API_BASE_URL=https://cloudcostsentinel.onrender.com` in the intended deployment environment. The value is the backend origin only, is public, and is embedded at build time. Redeploy after changing it. The backend CORS list must include the exact deployed frontend origin and any intentionally supported stable production alias; do not add wildcard origins.

## Verify after deployment

```sh
curl -i https://cloudcostsentinel.onrender.com/api/health/live
curl -i https://cloudcostsentinel.onrender.com/api/health/ready
curl -i https://cloudcostsentinel.onrender.com/api/health
curl -i https://cloudcostsentinel.onrender.com/api/demo/scenarios
```

The live probe should return 200. In `ENVIRONMENT=demo`, readiness should return 200 with database `connected` and providers `simulated`. Confirm browser analysis responses label the anomaly, Decider provider, and report as simulated. Restart/redeploy and confirm the persistent disk retains approvals. A public demo shares approval state between visitors and is not an authenticated tenant environment.

## Authenticated production

Production remains separate from this demo. It requires `AUTH_ENABLED=true`, real OIDC issuer/audience/JWKS, real non-mock provider configuration, exact HTTPS CORS origins, and `DATABASE_PATH` on a mounted persistent disk. PostgreSQL and the browser OIDC login flow are not implemented yet, so this repository is not production ready.
