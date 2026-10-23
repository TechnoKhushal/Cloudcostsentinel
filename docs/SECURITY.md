# Security Architecture & Threat Model — CloudCost Sentinel

## 1. Overview & Threat Model

CloudCost Sentinel is a cloud cost decision-support application. Its default decision and report providers are simulated. Live integrations require explicit configuration and separate verification.

### Trust Boundaries
1. **Frontend to API Gateway / Reverse Proxy**: Web client to FastAPI backend. Protected by OIDC/OAuth2 Bearer tokens in production or local development mode.
2. **API Backend to Strands Decider**: In HTTP mode, calls `strands-decider serve` via typed REST SystemOne wire protocol.
3. **API Backend to Amazon Bedrock**: Strictly read-only generative analysis via AWS Bedrock Converse API using IAM credentials.
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
- It requires mock Decider and report providers, prohibits Cost Explorer and real notifications, accepts synthetic scenario IDs only, and marks the shared review queue as demo data.
- Per-process limits do not coordinate across multiple replicas. Use one instance or add shared rate limiting before scaling.
- SQLite needs a persistent mounted disk for records to survive redeploys. `DATABASE_URL` is rejected because PostgreSQL is not implemented.
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

### Amazon Bedrock Least-Privilege Policy
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvokeModelReadOnly",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    }
  ]
}
```

---

## 6. Secrets Management & Logging

- **No Secrets in Source**: `.env`, credentials, local SQLite databases, and benchmark results are strictly ignored in `.gitignore`.
- **Log Redaction**: Account IDs in AWS Cost Explorer status checks are masked (e.g. `***1234`). Secret keys and session tokens are never logged.
- **Health Endpoint Safety**: `/api/health` reports provider states (`simulated`, `configured_unverified`, `connected`) without exposing endpoints with credentials, private IP addresses, or internal tokens.
