# Security Architecture & Threat Model — CloudCost Sentinel

## 1. Overview & Threat Model

CloudCost Sentinel is a cloud cost decision-support application. Development/demo mode uses synthetic scenarios; production requires Supabase Auth, user-JWT PostgREST access, PostgreSQL RLS, and private report storage. Production live AWS ingestion uses customer-owned read-only IAM roles and short-lived STS credentials. **The migrations and production environment still require live-project application and verification; the deployed Render service is currently in explicit demo mode. Do not use it for private customer billing data until those gates pass.**

### Trust Boundaries
1. **Frontend to API**: Supabase Auth signs users in. The API verifies JWT signature, issuer, audience, and expiry, resolves the user's workspace, and carries the caller JWT to PostgREST so RLS applies to each query.
2. **API Backend to Strands Decider**: In HTTP mode, calls `strands-decider serve` via typed REST SystemOne wire protocol.
3. **API Backend to OpenRouter**: Optional bounded report generation with a backend-only key. Resource data is treated as untrusted evidence; no cloud credentials or mutation tools are provided to the model.
4. **API Backend to AWS**: A platform IAM identity with only `sts:AssumeRole` assumes a per-workspace `CloudCostSentinelReadOnly` role using a unique external ID. The customer role grants only `ce:GetCostAndUsage`; assumed credentials last 15 minutes. Queries avoid grouping and pagination, limiting each explicit analysis to one Cost Explorer request. AWS charges $0.01 per request.

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
  - Validates Supabase JWT tokens against the configured issuer/JWKS.
  - Claims checked: `iss` (issuer), `aud` (audience), `exp` (expiration), signature verification via JWKS.
  - Role-Based Access Control:
    - Workspace members can read data allowed by their role and trigger bounded cost analysis.
    - Owners/admins manage AWS role connections and workspace budget settings.
    - Reviewers may approve or reject internal review items; this never changes AWS resources.

### Development / Offline Mode
- In `ENVIRONMENT=development` with `AUTH_ENABLED=false`:
  - An explicit developer principal (`lead-cloud-engineer@company.internal`) is used with both viewer and reviewer privileges.
  - The API health endpoint (`/api/health`) displays a prominent warning: `auth.warning: "Authentication is disabled: development principal active."`
  - The UI displays `SIMULATED / DEMO MODE`.

### Public Simulated Demo
- `ENVIRONMENT=demo` is an explicit shared public demo, not a tenant-secure production mode.
- It requires the mock Decider, prohibits Cost Explorer and real notifications, accepts synthetic scenario IDs only, and marks the shared review queue as demo data. Reports use a clearly labeled deterministic fallback unless OpenRouter is explicitly configured.
- Per-process limits do not coordinate across multiple replicas. Use one instance or add shared rate limiting before scaling.
- The shared demo uses SQLite and synthetic data. Demo-mode data is not tenant-isolated and must not contain customer records.
- Supabase-authenticated workspace and AWS connection code exists, but the matching migrations must be applied and tested against a live Supabase project before production use.
- Signup provisions a personal workspace. Workspace invitations, member management, organization switching, billing subscriptions, and retention/deletion workflows are still missing.

---

## 4. Single-Transition Approval Idempotency & Audit Integrity

- **Replay Protection**:
  Approvals follow a strict state machine: `pending` -> `approved` | `rejected`.
  Submitting a decision on an already decided approval returns **`409 Conflict`**. Replay attempts or duplicate submissions are blocked atomically.
- **Reviewer Identity**:
  The `reviewed_by` field is **never** accepted from a client request body. The server derives the reviewer identity strictly from the verified JWT claims (`principal.email` or `principal.sub`).

---

## 5. Least-Privilege IAM Policies

The Render platform identity may use a rotatable key stored only in Render, with an identity policy limited to `sts:AssumeRole` on `arn:aws:iam::*:role/CloudCostSentinelReadOnly`. It must not have direct billing or resource mutation permissions. Each customer creates their own role with a unique per-workspace `sts:ExternalId` trust condition.

### Customer AWS Cost Explorer Role Permission
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
    }
  ]
}
```

The application returns the exact platform principal ARN and unique external ID for the customer's role trust relationship. Never request customer access keys; the backend uses 15-minute assumed-role credentials.

Generative explanations use OpenRouter's API from the backend only. Leave `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` unset to avoid external generative calls. Select an available model and review its current pricing/data terms before enabling it.

---

## 6. Secrets Management & Logging

- **No Secrets in Source**: `.env`, credentials, local SQLite databases, and benchmark results are strictly ignored in `.gitignore`.
- **Log Redaction**: Account IDs in AWS Cost Explorer status checks are masked (e.g. `***1234`). Secret keys and session tokens are never logged.
- **Health Endpoint Safety**: `/api/health` reports provider states (`simulated`, `configured_unverified`, `connected`) without exposing endpoints with credentials, private IP addresses, or internal tokens.
