# CloudCost Sentinel — Current Architecture

This page describes the code that exists in this repository. The public Render/Vercel deployment remains an explicitly shared synthetic demo. The production Supabase and customer-owned AWS paths are implemented in source, but their live project configuration and tenant-isolation behavior are not yet verified. See [production readiness](PRODUCTION_READINESS.md) and the detailed [execution flow](../flow.md).

## System view

```mermaid
flowchart LR
    Browser[React + TypeScript + Vite]
    Auth[Supabase Auth]
    API[FastAPI]
    AuthZ[JWT verification + workspace role]
    Source{Input source}
    Demo[Synthetic scenario registry]
    AWS[STS AssumeRole + Cost Explorer]
    Math[Deterministic cost analyzer]
    Policy[Rules or external Decider]
    Report[Optional OpenRouter narrator\n(or deterministic template)]
    Store{Repository}
    SQLite[(SQLite local/demo)]
    Supabase[(PostgREST + Postgres RLS)]
    Storage[(Private Supabase Storage)]

    Browser --> Auth
    Browser -->|Bearer token + API request| API
    API --> AuthZ
    AuthZ --> Source
    Source --> Demo
    Source --> AWS
    AWS --> Math
    Demo --> Math
    Math --> Policy
    Math --> Report
    Policy --> Report
    Report --> Store
    Store --> SQLite
    Store --> Supabase
    Report -. private object .-> Storage
    Store -->|JSON response| Browser
```

## Request lifecycle

1. `frontend/src/main.tsx` mounts `AuthGate`, `ErrorBoundary`, and `App`.
2. `AuthGate` restores the browser Supabase session when configured. `frontend/src/api.ts` sends the access token to the configured FastAPI origin.
3. `backend/main.py` applies host validation, CORS, request-size/demo limits, request IDs, safe response headers, and API routing.
4. Protected route dependencies in `backend/auth.py` verify the JWT, resolve a Supabase workspace, enforce viewer/reviewer/admin role, and set a caller-token request scope.
5. `analyze_anomaly` selects permitted synthetic input in development/demo or the saved customer role in production. Production configuration refuses disabled AWS ingestion and mock decisions.
6. `AWSCostExplorerService` assumes the customer-owned read-only role with a workspace external ID and queries bounded Cost Explorer data. The durable Supabase quota limits billable workspace queries.
7. `cost_analyzer.py` computes metrics; `decider_client.py` produces a policy decision; confidence/error safeguards fail toward human review.
8. `narrator.py` may send a bounded metric summary to OpenRouter when configured. The deterministic fallback works without the AI provider, and the narrator cannot change the decision.
9. The repository persists a tenant-scoped analysis bundle. Production calls PostgREST/Storage using the caller's JWT so database RLS remains the tenant boundary. Local/demo uses SQLite.
10. The UI displays source and quality labels, restores the latest saved analysis, and supports internal approval review. An approval does not mutate AWS resources.

## Module responsibilities

| Area | Location | Responsibility |
| --- | --- | --- |
| API composition and route handlers | `backend/main.py` | Lifespan, request middleware, validation, role dependencies, provider orchestration, and response contracts. |
| Configuration and auth | `backend/config.py`, `backend/auth.py` | Environment validation, Supabase JWT verification, workspace resolution, and RBAC. |
| Persistence adapters | `backend/database/` | SQLite for development/demo; Supabase caller-token PostgREST and private Storage for production. |
| Domain schemas | `backend/models/` | Typed cost anomalies, decisions, approvals, and reports. |
| Provider/domain services | `backend/services/` | Cost formulas, AWS ingestion, policy client, grounded report generation, and notification adapter. |
| Browser UI | `frontend/src/` | Screens, auth gate, typed API client, visualizations, and state orchestration. |
| Database schema | `supabase/migrations/` | Ordered tenant tables, policies, RPCs, workspace AWS settings, and readiness contract. |
| Verification | `tests/`, `frontend/tests/`, `.github/workflows/ci.yml` | Backend/frontend suites, SQL migration smoke checks, and container build smoke. |

## Trust and deployment boundaries

- **Production persistence:** Supabase Auth + caller-JWT PostgREST/Postgres RLS + private Storage. No service-role key or direct database password belongs in the app request path.
- **Cloud data:** Customer-owned IAM role, unique per-workspace external ID, short-lived STS credentials, and `ce:GetCostAndUsage`. No infrastructure mutation permissions.
- **AI:** Optional server-side OpenRouter credentials only. Send a bounded metric summary; do not send AWS keys, role credentials, or raw account identifiers.
- **Demo:** Shared, unauthenticated, synthetic data and SQLite. Demo records are not private or durable. The demo write limiter is process-local and is suitable only for a single instance.
- **Production readiness:** AWS query allowance is tenant-scoped and durable. Authenticated production routes consume fixed per-user rolling-window limits from Supabase after JWT and role verification. A shared-store failure denies protected requests. Public liveness/readiness probes remain unauthenticated for platform health checks.

## Known product boundaries

- Personal workspaces exist; invitations and multi-member organization administration do not.
- Notification adapters support disabled, mock, and AWS SNS. Mock delivery is not real delivery.
- Subscription payments, account deletion/retention automation, and support operations are not implemented.
- Hosted Supabase migrations/RLS, actual customer AWS roles, auth email delivery, and production deployment settings still need live verification.
