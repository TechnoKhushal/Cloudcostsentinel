# CloudCost Sentinel — Production Hardening Log

**Date:** 2026-10-23  
**Repository:** https://github.com/TechnoKhushal/Cloudcostsentinel  
**Status:** Hardened, Verified & Tested  

---

## 1. Baseline Audit & Remediation Summary

| Lead Area | Finding | Remediation Implemented | Status |
| :--- | :--- | :--- | :--- |
| **P0: `decider_client.py` In-Process Fake Stub** | `_call_inprocess_decider()` was returning mock numbers while pretending to load `StrandsDeciderModel`. | Disabled in-process provider; raised explicit `NotImplementedError` explaining official model is served via HTTP (`strands-decider serve`). | Verified |
| **P0: Self-Referential Decider Endpoint Ambiguity** | `STRANDS_DECIDER_URL` defaulted to `http://127.0.0.1:8000/v1/systemone`, pointing back to the app's heuristic route. | Repointed default `STRANDS_DECIDER_URL` to external `http://127.0.0.1:8080/v1/systemone`. Added startup guard preventing HTTP decider from pointing to application's own port. Tagged reference endpoint with `X-Sentinel-Test-Fixture: true`. | Verified |
| **P0: Model Identity Truthfulness** | When `mock` provider executed, trace must never report real model ID. | Strictly enforce `provider="mock-simulated"` and `model_id="demo-policy-evaluator-v1"` for mock runs. Record both `raw_model_action` and `effective_action` separately so audit log never conflates model choice with safety overrides. | Verified |
| **P0: Decider Response Validation** | Live Decider outputs must be validated for action set, probability bounds, and sum tolerance. | Added strict response validation in `decider_client.py`: checks finite values, 0.0-1.0 range, sum within 5% tolerance, confidence bounds. Fails closed to `request_approval` on error. | Verified |
| **P0: Honest Readiness Checks** | `get_health()` returned `ready: true` regardless of real connectivity. | Implemented `/api/health/live` (cheap liveness) and `/api/health` with granular provider states (`simulated`, `configured_unverified`, `connected`, `disabled`). Masked account secrets. | Verified |
| **P0: Security & Auth** | No authentication on approvals; client supplied `reviewed_by`. | Created `backend/auth.py` with JWT Bearer validation and RBAC (`reviewer` vs `viewer`). In production, unauthenticated requests return 401. Server extracts `reviewed_by` strictly from token claims. | Verified |
| **P0: Single-Transition Idempotency** | Replay of approval decisions allowed arbitrary re-decisions. | `db.update_approval_status()` atomically updates only when status is `pending`; raises `ApprovalConflictError` (HTTP 409 Conflict) on replay. | Verified |
| **P0: CORS & Request Limits** | CORS origins parsing broke with JSON-like arrays; limits missing `ge=1`. | Implemented `parse_cors_origins()` supporting both JSON lists and comma-separated strings. Added `ge=1, le=100` for `limit` and validated `scenario_id` (422 on invalid). | Verified |
| **P1: Cost Explorer & Date Math** | Fixed `current_day_of_month=18` broke month calculations; exclusive end dates in AWS Cost Explorer unhandled; pagination missing; single-service breakdown lost. | Dynamically compute real month days with `calendar.monthrange()`; use timezone-aware UTC dates; handle CE exclusive end date; added pagination loop (`NextPageToken`); preserved top contributing service and per-service breakdown. | Verified |
| **P1: Notification Abstraction** | `notify_owner` returned simulated string without provider abstraction. | Created `backend/services/notification_service.py` with `disabled`, `mock`, and `sns` providers. Refuses to send to placeholder `.internal` or `unknown` recipients. | Verified |
| **P1: Persistence & SQLite Integrity** | `is_simulated` flag not persisted in SQLite; WAL mode missing; timezone-naive timestamps. | Added `is_simulated INTEGER DEFAULT 1` with automatic column migration; enabled WAL mode and busy timeout; used `datetime.now(timezone.utc)`. | Verified |
| **P1: Bedrock Extraction & Fallback** | JSON extracted with naive substring search; could override Decider action. | Hardened JSON parsing with markdown block stripping, field truncation/bounding, and explicit fallback status labels (`demo-narrative-adapter`, `is_simulated=True`). | Verified |
| **P1: Frontend URL & Race Conditions** | Hardcoded `http://127.0.0.1:8000`; scenario switching had race conditions; browser `alert()` used. | Supported `VITE_API_BASE_URL` with same-origin fallback; added `AbortController` cancellation on scenario change; replaced browser `alert()` with accessible inline toasts; removed client-side `reviewed_by`. | Verified |
| **P1: Multi-Stage Dockerfile & Compose** | Root Dockerfile only built backend; Compose claimed production with mock data. | Created multi-stage `Dockerfile` (Node 20 builder + Python 3.11 runtime with non-root user and healthcheck). Relabeled `docker-compose.yml` to `demo` environment. | Verified |
| **P1: CI Lockfile & Scripts** | CI used `npm ci || npm install` and loose `pip install`. Benchmark claimed real measurement for mock. | Updated CI to use canonical `requirements.txt` and strict `npm ci`. Fixed benchmark script to label mock runs as `simulated_mock_execution`. | Verified |

---

## 2. Verification Commands & Results

| Command | Target | Result | Notes |
| :--- | :--- | :--- | :--- |
| `python -m compileall -q backend patterns scripts tests` | Python Syntax & Bytecode | **PASS** | 0 compilation errors across all modules. |
| `python -m pytest tests/ -v` | Backend Test Suite | **PASS** | 22/22 tests passing (spend math, decider fallback, auth, 409 conflict, CORS, validation). |
| `python -m pytest patterns/ -v` | Reusable Pattern Tests | **PASS** | 5/5 tests passing (Strands interventions, Proceed/Guide/Confirm actions). |
| `python patterns/threshold_aware_anomaly_response/standalone_example.py` | Standalone Policy Script | **PASS** | Evaluated 3 anomalies deterministically. |
| `npm run lint` (in `frontend/`) | Frontend Oxlint | **PASS** | 0 warnings, 0 errors across 13 files. |
| `npm run build` (in `frontend/`) | TypeScript & Vite Bundle | **PASS** | `tsc -b && vite build` built clean bundle in `frontend/dist/`. |
