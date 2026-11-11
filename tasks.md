# CloudCost Sentinel — 100-step production plan

This is the delivery checklist for the existing CloudCost Sentinel repository. Work proceeds in order, one phase per user “go”. A task is checked only after its implementation and the phase acceptance checks are complete. Phase 1 is complete; all later tasks remain open.

## Phase 1 — Product, architecture, and risk audit (complete)

- [x] 1. Identify the current product, target users, and intended production outcome from the repository and request.
- [x] 2. Inventory the frontend, API, persistence, authentication, AWS ingestion, AI explanation, notification, and migration modules.
- [x] 3. Trace the current browser-to-API and API-to-provider execution paths in `flow.md`.
- [x] 4. Record architecture decisions, provider boundaries, and rationale in `decisions.md`.
- [x] 5. Define the ten delivery phases, their task IDs, and completion gates in this checklist.
- [x] 6. Classify existing integrations as required, optional, or conditional; include external APIs that the production features actually need.
- [x] 7. Record known production gaps from source documentation, including unverified live Supabase, AWS, and hosted deployment configuration.
- [x] 8. Identify the privacy, security, accessibility, SEO, legal, and customer trust risks to address in later phases.
- [x] 9. Set truthful product boundaries: read-only cloud data, no autonomous cloud mutation, and no unsupported savings or compliance claims.
- [x] 10. Define release evidence: automated tests, tenant-isolation checks, real-provider checks, browser checks, operational readiness, and deployment verification.

## Phase 2 — Repository foundations and secure configuration

- [ ] 11. Reconcile README, architecture, setup, and deployment documentation with the actual current code paths.
- [ ] 12. Establish and document a clean module and package structure without breaking imports or migrations.
- [ ] 13. Inventory dependencies, licenses, known vulnerabilities, unused packages, and supported runtime versions.
- [ ] 14. Audit tracked files, Git history, ignore rules, build artifacts, and secret exposure.
- [ ] 15. Make environment variable schemas consistent across backend, Vercel, Render, and local development.
- [ ] 16. Fail closed on missing, malformed, or contradictory production configuration.
- [ ] 17. Verify HTTPS, exact CORS origins, security headers, trusted hosts, and proxy behavior.
- [ ] 18. Replace process-local production rate limits with shared limits or an explicitly justified hosted control.
- [ ] 19. Add structured redacted logs, request IDs, safe error responses, and actionable health/readiness states.
- [ ] 20. Complete phase-level lint, type checks, tests, dependency checks, and configuration documentation.

## Phase 3 — Identity, workspace, and tenant authorization

- [ ] 21. Verify Supabase Auth configuration and supported JWT signing/rotation behavior.
- [ ] 22. Complete sign-up, email verification, sign-in, sign-out, password reset, and expired-session UX.
- [ ] 23. Configure production SMTP and verify auth email deliverability and redirect allowlists.
- [ ] 24. Review workspace provisioning, membership roles, ownership changes, and account recovery.
- [ ] 25. Audit every API route for authentication and least-privilege role enforcement.
- [ ] 26. Verify RLS on every tenant-owned table, RPC, and private storage object.
- [ ] 27. Test cross-tenant read/write, IDOR, role escalation, replay, and token-expiry attempts.
- [ ] 28. Add explicit data export and account deletion flows with authorization and audit records.
- [ ] 29. Define consent, retention, deletion, and backup behavior for customer data and generated reports.
- [ ] 30. Pass two-user end-to-end identity and isolation checks on a dedicated Supabase project.

## Phase 4 — Customer AWS connection and live cost ingestion

- [ ] 31. Review the external-ID, role ARN, account ID, and owner-only AWS connection flow.
- [ ] 32. Verify the platform identity can assume only the intended customer role patterns.
- [ ] 33. Verify the customer role can read only required cost data and cannot mutate AWS resources.
- [ ] 34. Validate role ARNs/account IDs and defend against confused-deputy and account-mismatch cases.
- [ ] 35. Test STS timeouts, throttles, denial, expired sessions, and AWS region failures.
- [ ] 36. Make Cost Explorer date ranges, currency, data freshness, partial pages, and source provenance explicit.
- [ ] 37. Verify durable tenant query quotas and protection against repeated/costly calls.
- [ ] 38. Show AWS's current request cost and data-lag limitations before connection and analysis.
- [ ] 39. Run integration tests using an isolated AWS test account/role; never require production customer credentials in CI.
- [ ] 40. Pass an end-to-end live cost ingestion test and confirm no cloud write permissions are requested.

## Phase 5 — Analysis, recommendations, reports, and truthful behavior

- [ ] 41. Review cost formulas, baseline windows, forecast assumptions, currency, and sparse-data behavior.
- [ ] 42. Version and document the deterministic policy and its thresholds.
- [ ] 43. Validate decision provider errors, confidence, malformed responses, and safe fallback behavior.
- [ ] 44. Keep AI narrative optional, backend-only, grounded in evidence, and unable to change policy decisions.
- [ ] 45. Validate AI input minimization, output schema, timeouts, retry budgets, and disclosure.
- [ ] 46. Label simulated, observed, stale, partial, and unavailable data consistently in API and UI.
- [ ] 47. Verify analysis/report persistence and restore behavior for each tenant.
- [ ] 48. Make report exports accurate, private, accessible, and free of fabricated savings claims.
- [ ] 49. Test boundary cases: refunds, zero baseline, missing days, month boundaries, multiple currencies, and stale AWS data.
- [ ] 50. Pass analysis and decision regression tests using real fixtures plus deterministic property/boundary cases.

## Phase 6 — Persistence, operational workflows, and notifications

- [ ] 51. Rehearse all Supabase migrations against a clean isolated project and a prior-version upgrade.
- [ ] 52. Verify rollback/recovery procedures, backup restoration, and schema readiness checks.
- [ ] 53. Verify approval transitions are atomic, tenant-scoped, idempotent, and auditable.
- [ ] 54. Define report/object retention and clean up orphaned storage objects safely.
- [ ] 55. Decide whether notification delivery is a launch requirement; do not report mock delivery as real.
- [ ] 56. If notifications launch, configure an actual delivery provider and authenticated, tenant-scoped dispatch.
- [ ] 57. Add opt-in, unsubscribe, delivery status, retry/dead-letter behavior, and notification preferences as applicable.
- [ ] 58. Verify webhook signatures and replay handling for every provider webhook introduced.
- [ ] 59. Add operational runbooks for outages, quota exhaustion, suspected tenant exposure, and AWS access revocation.
- [ ] 60. Pass persistence, approval concurrency, object-access, and notification delivery checks.

## Phase 7 — Customer-ready frontend and accessibility

- [ ] 61. Map every visible screen and action to a working API or explicitly label it unavailable.
- [ ] 62. Remove dead navigation, placeholder copy, fake counters, unsupported reviews, and inert buttons.
- [ ] 63. Complete responsive layouts, mobile menu behavior, and horizontal-overflow checks.
- [ ] 64. Verify forms, validation, success/error states, empty states, loading, and retry behavior.
- [ ] 65. Verify keyboard navigation, focus management, semantic headings, accessible names, and screen-reader status.
- [ ] 66. Audit color contrast, reduced motion, touch targets, charts, and non-color status cues.
- [ ] 67. Add useful page titles, descriptions, favicon, 404 experience, and correct business/contact details.
- [ ] 68. Check images, fonts, icons, and UI assets for licenses, attribution needs, alt text, size, and loading.
- [ ] 69. Test supported browsers and narrow, medium, and wide viewport sizes.
- [ ] 70. Complete a browser-based walkthrough of each customer journey and record outcomes.

## Phase 8 — Privacy, legal readiness, SEO, and product trust

- [ ] 71. Map personal data, AWS billing data, processors, storage locations, logs, and data flows.
- [ ] 72. Draft privacy, terms, cookie, acceptable-use, and billing/refund policies for qualified business review.
- [ ] 73. Determine whether consent management is required from actual cookies, analytics, and third-party embeds.
- [ ] 74. Minimize collection and define retention, access, correction, deletion, and export processes.
- [ ] 75. Review India DPDP Act/rules applicability, notices, consent, children's data, processors, and breach response with counsel.
- [ ] 76. Review applicable non-India privacy, consumer, subscription, tax, and accessibility obligations for launch regions.
- [ ] 77. Verify business identity/contact details, renewal/cancellation disclosures, prices, taxes, and refund terms.
- [ ] 78. Audit third-party SDKs, trackers, training/data use, DPAs, and consent gating.
- [ ] 79. Improve crawlability, canonical metadata, sitemap/robots, structured data, headings, and original content without keyword stuffing.
- [ ] 80. Remove unsubstantiated performance/security/compliance promises and document claims that need evidence.

## Phase 9 — Commercial services and customer lifecycle

- [ ] 81. Decide the launch business model, plans, billing cadence, trials, and cancellation rules before implementing billing.
- [ ] 82. If subscriptions launch, choose and configure an India-capable payment provider after business/KYC eligibility review.
- [ ] 83. Implement server-side checkout/session creation and signed, replay-safe billing webhooks if billing is in scope.
- [ ] 84. Enforce subscription entitlements on the API, not only in the frontend.
- [ ] 85. Implement billing history, invoices/receipts, cancellation, failed-payment recovery, and refund/support workflows as required.
- [ ] 86. Set up production authentication email delivery with a verified sending domain and deliverability controls.
- [ ] 87. Add customer support/contact flows, response expectations, and a secure support-data handling process.
- [ ] 88. Add product analytics only if justified, privacy reviewed, minimized, and consent-gated where required.
- [ ] 89. Make integrations optional and replaceable; never require DigiLocker or unrelated identity data without a demonstrated need.
- [ ] 90. Test complete signup-to-cancel lifecycle, entitlements, payment failures, refund paths, and webhook replay if billing is included.

## Phase 10 — Release assurance, deployment, and ongoing operations

- [ ] 91. Run backend, frontend, migration, browser, and API contract tests on the final candidate revision.
- [ ] 92. Run dependency/security scanning and resolve or explicitly triage release-blocking findings.
- [ ] 93. Run performance, load, timeout, quota, and graceful-degradation checks.
- [ ] 94. Review secrets and production environment settings without copying secrets into source or chat.
- [ ] 95. Verify production backup, restore, incident response, data deletion, and access revocation drills.
- [ ] 96. Deploy backend only after real Supabase, AWS, email, and any launch-critical provider configuration is verified.
- [ ] 97. Deploy frontend only after API origin, auth redirects, CORS, and public build variables are verified.
- [ ] 98. Run post-deploy smoke, auth, tenant isolation, AWS ingestion, report, and mobile-browser checks.
- [ ] 99. Verify monitoring, alerts, support ownership, cost budgets, and rollback procedure.
- [ ] 100. Record release evidence, known limitations, operator handoff, and final production-readiness decision.

## Phase completion rule

A phase is complete only when all ten tasks in that phase are checked and its release evidence is recorded. Do not claim production readiness while any required external project configuration or tenant-isolation check remains unverified.
