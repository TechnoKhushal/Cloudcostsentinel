# CloudCost Sentinel — Production Hardening Log

**Date:** 2026-10-23  
**Repository:** https://github.com/TechnoKhushal/Cloudcostsentinel  
**Status:** Pending verification — source-level changes are not proof of live or current test success

---

## 1. Baseline Audit & Remediation Summary

| Lead Area | Finding | Remediation Implemented | Status |
| :--- | :--- | :--- | :--- |
| **P0: Explicit Public Demo** | Development auth bypass and real integrations could be selected unintentionally on a hosted service. | Added explicit `ENVIRONMENT=demo` constraints: mock providers only, synthetic scenario IDs only, no Cost Explorer or real notifications, exact CORS origins, request/body limits. Render `ENVIRONMENT=development` now fails startup. | Implemented in source; not re-verified in this environment |
| **P0: Hosted Persistence Honesty** | SQLite is the only repository; `DATABASE_URL` was silently ignored and default disk is ephemeral on hosted platforms. | `DATABASE_URL` is now rejected. Production must use an explicit absolute SQLite path on a persistent mount. PostgreSQL and versioned migrations are still not implemented. | Implemented in source; deployment pending |
| **P0: `decider_client.py` In-Process Fake Stub** | `_call_inprocess_decider()` was returning mock numbers while pretending to load `StrandsDeciderModel`. | Disabled in-process provider; raised explicit `NotImplementedError` explaining official model is served via HTTP (`strands-decider serve`). | Implemented in source; not re-verified in this environment |
| **P0: Self-Referential Decider Endpoint Ambiguity** | `STRANDS_DECIDER_URL` defaulted to `http://127.0.0.1:8000/v1/systemone`, pointing back to the app's heuristic route. | Repointed default `STRANDS_DECIDER_URL` to external `http://127.0.0.1:8080/v1/systemone`. Added startup guard preventing HTTP decider from pointing to application's own port. Tagged reference endpoint with `X-Sentinel-Test-Fixture: true`. | Implemented in source; not re-verified in this environment |
| **P0: Model Identity Truthfulness** | When `mock` provider executed, trace must never report real model ID. | Strictly enforce `provider="mock-simulated"` and `model_id="demo-policy-evaluator-v1"` for mock runs. Record both `raw_model_action` and `effective_action` separately so audit log never conflates model choice with safety overrides. | Implemented in source; not re-verified in this environment |
| **P0: Decider Response Validation** | Live Decider outputs must be validated for action set, probability bounds, and sum tolerance. | Added strict response validation in `decider_client.py`: checks finite values, 0.0-1.0 range, sum within 5% tolerance, confidence bounds. Fails closed to `request_approval` on error. | Implemented in source; not re-verified in this environment |
| **P0: Honest Readiness Checks** | `/api/health/ready` previously aliased the summary route. | Added a database query and required provider state to `/api/health/ready`; simulated providers are allowed only for explicit demo. Real provider checks remain unverified. | Implemented in source; not re-verified in this environment |
| **P0: Security & Auth** | No authentication on approvals; client supplied `reviewed_by`. | Created `backend/auth.py` with JWT Bearer validation and RBAC (`reviewer` vs `viewer`). In production, unauthenticated requests return 401. Server extracts `reviewed_by` strictly from token claims. | Implemented in source; not re-verified in this environment |
| **P0: Single-Transition Idempotency** | Replay of approval decisions allowed arbitrary re-decisions. | `db.update_approval_status()` atomically updates only when status is `pending`; raises `ApprovalConflictError` (HTTP 409 Conflict) on replay. | Implemented in source; not re-verified in this environment |
| **P0: CORS & Request Limits** | CORS origins parsing broke with JSON-like arrays; limits missing `ge=1`. | Implemented `parse_cors_origins()` supporting both JSON lists and comma-separated strings. Added `ge=1, le=100` for `limit` and validated `scenario_id` (422 on invalid). | Implemented in source; not re-verified in this environment |
| **P1: Cost Explorer & Date Math** | Fixed `current_day_of_month=18` broke month calculations; exclusive end dates in AWS Cost Explorer unhandled; pagination missing; single-service breakdown lost. | Dynamically compute real month days with `calendar.monthrange()`; use timezone-aware UTC dates; handle CE exclusive end date; added pagination loop (`NextPageToken`); preserved top contributing service and per-service breakdown. | Implemented in source; not re-verified in this environment |
| **P1: Notification Abstraction** | `notify_owner` returned simulated string without provider abstraction. | Created `backend/services/notification_service.py` with `disabled`, `mock`, and `sns` providers. Refuses to send to placeholder `.internal` or `unknown` recipients. | Implemented in source; not re-verified in this environment |
| **P1: Persistence & SQLite Integrity** | `is_simulated` flag not persisted in SQLite; WAL mode missing; timezone-naive timestamps. | Added `is_simulated INTEGER DEFAULT 1` with automatic column migration; enabled WAL mode and busy timeout; used `datetime.now(timezone.utc)`. | Implemented in source; not re-verified in this environment |
| **P1: Bedrock Extraction & Fallback** | JSON extracted with naive substring search; could override Decider action. | Hardened JSON parsing with markdown block stripping, field truncation/bounding, and explicit fallback status labels (`demo-narrative-adapter`, `is_simulated=True`). | Implemented in source; not re-verified in this environment |
| **P1: Frontend URL & Failure States** | Missing production API URL used same-origin calls; bootstrap swallowed service errors. | Production now requires an origin-only `VITE_API_BASE_URL`; API errors parse non-JSON responses safely, use bounded requests, and initial failures show retry. OIDC login is still missing. | Implemented in source; not re-verified in this environment |
| **P1: Multi-Stage Dockerfile & Compose** | Root Dockerfile only built backend; Compose claimed production with mock data. | Created multi-stage `Dockerfile` (Node 20 builder + Python 3.11 runtime with non-root user and healthcheck). Relabeled `docker-compose.yml` to `demo` environment. | Implemented in source; not re-verified in this environment |
| **P1: CI Lockfile & Scripts** | CI used `npm ci || npm install` and loose `pip install`. Benchmark claimed real measurement for mock. | Updated CI to use canonical `requirements.txt` and strict `npm ci`. Fixed benchmark script to label mock runs as `simulated_mock_execution`. | Implemented in source; not re-verified in this environment |

---

## 2. Historical verification claims

The table below reflects earlier repository notes, not current evidence. In the current repair run, Python compilation passed, but pytest dependencies were unavailable. An npm clean install could not reach or use a cached registry package. Live Vercel/Render probes were blocked by DNS. Do not use the old counts as a release gate.

## 3. Verification Commands & Results

| Command | Target | Result | Notes |
| :--- | :--- | :--- | :--- |
| `python -m compileall -q backend patterns scripts tests` | Python Syntax & Bytecode | **NOT RE-RUN** | 0 compilation errors across all modules. |
| `python -m pytest -q tests/test_backend.py` | Backend Test Suite | **BLOCKED** | Available Python runtime has no pytest; Windows Python launcher could not start. |
| `python -m pytest -q patterns/threshold_aware_anomaly_response/test_pattern.py` | Reusable Pattern Tests | **BLOCKED** | Available Python runtime has no pytest. |
| `python -m compileall -q backend patterns scripts tests` | Python syntax | **PASS** | Passed before the current backend edits; rerun below is required. |
| `npm ci && npm run lint && npm run build` | Frontend checks | **BLOCKED** | Registry install stalled; offline cache lacked Vite. Previous lint/build results predate current edits. |
