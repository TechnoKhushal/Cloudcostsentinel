# CloudCost Sentinel — Decision record

This log records decisions made during the staged productionization. New implementation decisions should be appended with date, choice, reason, alternatives, and impact. The initial audit decisions below describe the current plan; they do not claim external services are configured.

## 2026-11-12 — Phase 1 baseline decisions

### D-001: Treat the current repository as the product baseline

**Choice:** Scope the 100-step plan to CloudCost Sentinel, the current repository's cloud cost decision-support product.

**Reason:** The supplied description contains an empty product-description quotation, while the existing code and README describe CloudCost Sentinel. The repository is the best available source of concrete product behavior.

**Impact:** The plan covers its existing React/Vite frontend, FastAPI backend, AWS cost ingestion, tenant persistence, Supabase auth, operational reports, and the commercial/privacy work required before customer launch. Ask for correction only if the intended product is different.

### D-002: Separate required product APIs from optional and conditional providers

**Choice:** Keep the architecture provider-based and use an API only when a real product behavior requires it. Classify provider integrations as core, optional, or conditional instead of treating every named example as mandatory.

**Reason:** The source prompt names example services but also asks for real data and a sellable product. A payment or AI API should not be added unless the associated customer-facing feature is part of launch.

**Current API map:**

| Capability | Status | API/service boundary | Why it exists / launch condition |
| --- | --- | --- | --- |
| User identity and sessions | Core for customer accounts | Supabase Auth endpoints/JWKS | Sign-up, verification, sign-in, recovery, and bearer-token validation. Production requires a real project and production email delivery. |
| Tenant persistence | Core | Supabase PostgREST/PostgreSQL with RLS; Supabase Storage for private report objects | Tenant-owned records and private report files. Caller JWT and database policies must enforce tenant scope. |
| Real cloud cost data | Core product differentiator | AWS STS `AssumeRole` plus AWS Cost Explorer `GetCostAndUsage` | Customer-owned read-only role connection and live billing telemetry. Use explicit per-workspace role trust; never request resource mutation permissions. |
| Explanations | Optional | Existing backend-only OpenRouter API adapter, or deterministic local explanation | Narrative is not required to analyze costs and must never decide or execute cloud actions. AI provider/model availability and price are not guaranteed by this plan. |
| Authentication email | Required for public email/password account lifecycle | SMTP delivery configured in Supabase Auth with a production provider such as AWS SES or Resend | Verification and recovery emails must reach actual customers; Supabase's built-in sender is not a production delivery dependency. Choose provider after domain/account setup. |
| Anomaly/approval notifications | Conditional | Existing notification adapter supports disabled/mock/SNS/SES | Add a real provider only if customers need out-of-app delivery in the launch scope; otherwise clearly show in-app-only status. |
| Subscription payments | Conditional for paid SaaS checkout | Payment provider API plus signed webhook endpoint; shortlist Razorpay for India-first launch, subject to merchant eligibility and business/legal review | Needed only if users can buy a paid subscription in-product. A payment API is not needed for a free/self-hosted release. Never trust frontend payment state. |
| Analytics, CAPTCHA, DigiLocker, maps, etc. | Not currently required | None selected | No demonstrated product requirement. Adding trackers or collecting identity data increases privacy, consent, and support obligations. |

**Cost implication:** AWS Cost Explorer API calls are billable; the current integration intentionally limits each explicit analysis to one request and should disclose current AWS pricing and data freshness before use. Query pricing can change and must be checked at release time.

### D-003: Keep human decision support read-only against customer infrastructure

**Choice:** The product can analyze, recommend, and record human review, but it does not terminate, resize, or modify customer AWS resources.

**Reason:** Billing anomalies alone do not provide enough operational context to safely mutate production systems. Least-privilege and human review reduce blast radius.

### D-004: Require explicit truth labels for data and provider status

**Choice:** Distinguish synthetic/demo, observed AWS, partial, stale, unavailable, simulated, deterministic, and externally generated results in product behavior.

**Reason:** Shared demo data and mocked providers are not acceptable evidence for a paid customer's cloud spend.

### D-005: Do not claim legal compliance or security certification from code changes

**Choice:** Later phases will identify obligations, implement technical controls, and prepare policy drafts, but applicability and legal text require qualified business/legal review.

**Reason:** India DPDP and other privacy/consumer obligations depend on business, data, geography, and processing facts not established by this repository. A website policy is not proof of compliance.

### D-006: Use release gates for external configuration

**Choice:** Do not switch hosted services to production mode or deploy customer traffic until live Supabase migrations/RLS, platform IAM, a customer AWS role, email delivery, and environment configuration are verifiable.

**Reason:** No connected Supabase/Render/Vercel dashboards or customer AWS account were available in the repository audit. CI mocks cannot prove those trust boundaries.

## Existing constraints observed

- Production adapter and six SQL migrations are present, but live project application is unverified.
- The public hosted service is documented as a shared synthetic demo, not a customer tenant service.
- Authentication, tenant-scoped repository, private reports, customer AWS role connection, AWS quota, and latest-analysis restore code already exist and must be audited rather than recreated.
- Signup provisions a personal workspace; invitations and organization member administration are not present.
- Notification mock/demo behavior exists; production notification delivery needs an explicit product decision.
- Subscription billing, retention/deletion lifecycle, and broader support operations are absent.
- The API examples and service providers are choices, not proof that credentials, free tiers, or production entitlements exist.

## 2026-11-12 — Phase 2 implementation decisions

### D-007: Derive Render Host validation from its injected public hostname

**Choice:** Add `TRUSTED_HOSTS` with Render's `RENDER_EXTERNAL_HOSTNAME` as the hosted default, exact CORS origins, and no credentialed cross-origin cookies. Disable the FastAPI schema/docs routes in production.

**Reason:** The application authenticates API calls with bearer tokens, and Render already supplies the service hostname. This avoids a new host-configuration secret/variable for the standard deployment while keeping custom API domains explicit.

**Impact:** Production startup rejects wildcard/invalid host allowlists; Vercel and Render retain HTTPS security headers. The obsolete `X-XSS-Protection` response header was removed. Inline styles remain allowed by CSP because several existing React components use them; inline scripts remain disallowed.

### D-008: Put production API rate counters in the existing Supabase database

**Choice:** Add migration `202611120001_shared_api_rate_limits.sql`, with an RLS-protected counter table and a `SECURITY DEFINER` RPC whose fixed thresholds cannot be chosen by the caller. Apply it after the existing six migrations and change the readiness contract to v7.

**Reason:** A process-local limiter does not coordinate across Render instances. Adding a separate Redis service would add secrets and operational dependencies; Supabase is already a required shared production service.

**Limits:** 120 general authenticated API requests/minute, 5 analyses/minute, and 3 AWS role verifications/minute per user. The durable daily AWS query quota remains an independent billing cap. If the RPC cannot be reached, protected production requests fail closed.

### D-010: Freeze direct workspace membership mutations until managed invitations exist

**Choice:** Migration `202611120002_lock_workspace_membership_writes.sql` keeps membership reads behind tenant RLS, revokes direct authenticated insert/update/delete privileges, and updates readiness to v8. The trusted `get_or_create_my_org()` provisioning flow can still create the initial owner. The supported role set includes `reviewer`.

**Reason:** There is no invitation or role-management API with audit records, ownership-transfer rules, or last-owner protection. The previous table grants let an owner/admin change membership roles directly through PostgREST, bypassing an application workflow. Blocking writes closes self-promotion and cross-member role escalation until that workflow is designed and tested.

**Limits:** Existing customers who already manage memberships directly must review this migration before applying it. Invitations, member administration, and account deletion remain unavailable; do not promise multi-user workspaces yet.

### D-009: Bound bodies at the ASGI receive boundary and keep provider errors redacted

**Choice:** Add `RequestBodyLimitMiddleware` that enforces a 64 KiB maximum even when a request omits `Content-Length`; include a sanitized request ID, response security headers, and generic 500 responses. Emit JSON logs through an explicit safe-field allowlist; request events include method/path/status/duration without query, body, or bearer data. Provider error responses/logs expose exception classes, not raw exception messages.

**Reason:** Checking only the declared length leaves a path for chunked bodies and raw dependency errors may reveal endpoints, identifiers, or provider response details.

### D-010: Keep environment templates canonical and avoid dependency growth

**Choice:** Keep backend/local variables in root `.env.example` and browser-public variables in `frontend/.env.example`; document the complete read set in README. Add no new environment variables for shared production rate limits and add no new dependency.

**Reason:** Supabase provides the shared rate-limit store, so another service would complicate setup without a product need. The existing dependency tree is sufficient.

**Audit evidence:** Current direct dependency inventories show declared licenses (Python runtime packages: MIT/BSD/Apache; npm direct packages: MIT/ISC/Apache), `npm audit` reports zero advisories, and `pip-audit -r requirements.txt` reports no known vulnerabilities. No unused direct dependency was identified in the frontend imports or backend requirements. A high-confidence credential-pattern scan of committed Git history found no matches (values were never printed).

### D-011: Make historical documentation snapshots explicit

**Choice:** Mark old architecture, Stitch, hardening, audit, and verification logs as historical where their statements no longer describe current source.

**Reason:** Historical audit counts and architecture claims could otherwise be mistaken for release evidence. Current architecture and production readiness now point to current source/CI and the explicit live-project gaps.
