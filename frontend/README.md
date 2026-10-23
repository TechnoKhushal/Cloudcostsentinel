# CloudCost Sentinel frontend

## Runtime behavior

The dashboard calls the FastAPI API directly. Production builds require `VITE_API_BASE_URL` to be set to the backend origin, for example `https://cloudcostsentinel.onrender.com`. Do not append `/api`; the API client adds each endpoint once. Vite embeds the value in the public bundle at build time, so redeploy after changing it. Never put secrets under `VITE_*`.

Health, scenarios, decision history, and approvals report failures independently. A refresh keeps previously loaded data and labels it as stale if a service is temporarily unavailable. Approval authorization remains server-side. The UI does not store or invent bearer tokens.

## Vercel deployment

- Root directory: `frontend`
- Framework preset: Vite
- Install command: `npm ci`
- Build command: `npm run build`
- Output directory: `dist`
- Set `VITE_API_BASE_URL=https://cloudcostsentinel.onrender.com` for the deployment environment and redeploy.
- Include the exact deployed frontend origin in Render's `CORS_ORIGINS` list. Do not use `*`.
- If the app should be public, verify Deployment Protection on the production domain. Keep preview deployments protected as appropriate.

The production API client fails with a visible configuration message when the base URL is missing or invalid. It never falls back to same-origin Vercel requests. The local development default is `http://127.0.0.1:8000`.

The backend demo is unauthenticated by design and must remain synthetic. An authenticated production API cannot be used interactively here because a complete OIDC sign-in flow is not implemented. Do not paste tokens into browser storage.

## Local development and checks

Use Node.js 24 and Python 3.11 for the checked-in CI toolchain. From `frontend/`, run:

```sh
npm ci
npm test
npm run lint
npm run build
```

Start FastAPI separately before using `npm run dev`. The API tests use Node's built-in test runner and require no extra test dependency.
