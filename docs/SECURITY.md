# Security Architecture & Threat Model — CloudCost Sentinel

## 1. Overview & Threat Model

CloudCost Sentinel is a cloud cost decision-support application. Its default decision provider is simulated and reports use an offline deterministic template unless OpenRouter is configured. Supabase schema foundations exist, but the API is not tenant-scoped and should not receive private customer data.

### Trust Boundaries
1. **Frontend to API Gateway / Reverse Proxy**: Web client to FastAPI backend. Generic OIDC bearer validation exists for production; browser sign-in and tenant ownership are not complete.
2. **API Backend to Strands Decider**: In HTTP mode, calls `strands-decider serve` via typed REST SystemOne wire protocol.
3. **API Backend to OpenRouter**: Optional bounded report generation with a backend-only key. Resource data is treated as untrusted evidence; no cloud credentials or mutation tools are provided to the model.
4. **API Backend to AWS Cost Explorer**: Read-only (`ce:GetCostAndUsage`) telemetry collection.

---

## 2. Zero-Mutation AWS Cloud Guarantee

**Non-Negotiable Rule**: CloudCost Sentinel never executes terminating, resizing, or mutative cloud actions.
- An **"Approval"** in Sentinel means: *A human cloud engineer reviewed the recommendation and verified the root-cause hypothesis.*
- Sentinel **never** terminates EC2 instances, modifies RDS parameters, deletes S3 buckets, or rewrites Auto Scaling policies.
- Downstream remediation execution remains strictly in customer change control systems (e.g. Terraform pipelines, ServiceNow, or manual CLI intervention).

---

## 3. Authentication & RBAC

### Architecture
- **Production Mode (`ENVIRONMENT=production`)**:
  - `AUTH_ENABLED=true` is required. Startup fails if OIDC/JWKS settings are missing. There is no authentication bypass.
  - Validates JWT tokens against OIDC identity provider (AWS Cognito, Auth0, Okta, Keycloak).
  - Claims checked: `iss` (issuer), `aud` (audience), `exp` (expiration), signature verification via JWKS.
  - Role-Based Access Control:
    - **`viewer`**: Can view telemetry, scenarios, decisions, and reports (`GET /api/decisions`, `GET /api/approvals`, `POST /api/analyze`).
    - **`reviewer`**: Can approve or reject pending remediation recommendations (`POST /api/approvals/{id}/decision`).

### Development / Offline Mode
- In `ENVIRONMENT=development` with `AUTH_ENABLED=false`:
  - An explicit developer principal (`lead-cloud-engineer@company.internal`) is used with both viewer and reviewer privileges.
  - The API health endpoint (`/api/health`) displays a prominent warning: `auth.warning: "Authentication is disabled: development principal active."`
  - The UI displays `SIMULATED / DEMO MODE`.

### Public Simulated Demo
- `ENVIRONMENT=demo` is an explicit shared public demo, not a tenant-secure production mode.
- It requires the mock Decider, prohibits Cost Explorer and real notifications, accepts synthetic scenario IDs only, and marks the shared review queue as demo data. Reports use a clearly labeled deterministic fallback unless OpenRouter is explicitly configured.
- Per-process limits do not coordinate across multiple replicas. Use one instance or add shared rate limiting before scaling.
- SQLite needs a persistent mounted disk for records to survive redeploys. `DATABASE_URL` is rejected because PostgreSQL is not implemented. Supabase migration SQL is not connected to the API.
- The frontend does not yet implement OIDC sign-in. Do not deploy it as an authenticated dashboard until that flow exists.

---

## 4. Single-Transition Approval Idempotency & Audit Integrity

- **Replay Protection**:
  Approvals follow a strict state machine: `pending` -> `approved` | `rejected`.
  Submitting a decision on an already decided approval returns **`409 Conflict`**. Replay attempts or duplicate submissions are blocked atomically.
- **Reviewer Identity**:
  The `reviewed_by` field is **never** accepted from a client request body. The server derives the reviewer identity strictly from the verified JWT claims (`principal.email` or `principal.sub`).

---

## 5. Least-Privilege IAM Policies

When deploying with live AWS integrations, use IAM roles for Amazon EC2 or ECS Task Execution roles instead of static long-lived credentials.

### AWS Cost Explorer Least-Privilege Policy
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CostExplorerReadOnly",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CallerIdentityForStatusCheck",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

Generative explanations use OpenRouter's API from the backend only. Leave `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` unset to avoid external generative calls. Select an available model and review its current pricing/data terms before enabling it.

---

## 6. Secrets Management & Logging

- **No Secrets in Source**: `.env`, credentials, local SQLite databases, and benchmark results are strictly ignored in `.gitignore`.
- **Log Redaction**: Account IDs in AWS Cost Explorer status checks are masked (e.g. `***1234`). Secret keys and session tokens are never logged.
- **Health Endpoint Safety**: `/api/health` reports provider states (`simulated`, `configured_unverified`, `connected`) without exposing endpoints with credentials, private IP addresses, or internal tokens.
