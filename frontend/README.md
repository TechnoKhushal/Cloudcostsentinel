# CloudCost Sentinel frontend

## Vercel deployment

- Root directory: `frontend`
- Framework: Vite
- Install command: `npm ci`
- Build command: `npm run build`
- Output directory: `dist`
- Set `VITE_API_BASE_URL` in both Preview and Production to the backend origin only, for example `https://your-api.example.com` (no `/api` suffix).
- Redeploy after changing this variable; Vite embeds it at build time. It is public and must never contain secrets.
- Configure the backend's exact HTTPS CORS origin for the deployed Vercel domain.

The API client intentionally fails with an actionable message in production if `VITE_API_BASE_URL` is missing or contains a path. It does not send production requests to the Vercel origin. In development it uses `http://127.0.0.1:8000`.

The backend's production mode requires OIDC bearer tokens. This frontend currently has no OIDC sign-in flow, so a production backend configured with authentication cannot be used interactively from this dashboard yet. Do not enter a fabricated token in browser storage; implement/configure a complete OIDC client before enabling authenticated dashboard access.

## Local development

From this directory, run `npm ci`, then `npm run dev`. Start FastAPI separately. Run `npm run lint` and `npm run build` before deployment.

---

## Vite template notes

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
