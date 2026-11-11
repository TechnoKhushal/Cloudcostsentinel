# CloudCost Sentinel — Cloud Cost Decision Support

[![CI](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/TechnoKhushal/Cloudcostsentinel/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tags](https://img.shields.io/badge/Tags-%23strands--decider--2b%20%7C%20%23policy-purple)](#hackathon-classification)

> **CloudCost Sentinel** reviews cost evidence and explains anomalies. The public deployment remains a synthetic demo. The API now contains a Supabase Auth, caller-JWT PostgREST and private-report Storage production path, but migrations have not been applied to a live project and production is not yet verified or ready for customer data.

---

## 1. Product Vision & The Signature Decision

In high-velocity cloud environments, cost anomalies force an operational dilemma:
- **Alert too often:** Alert fatigue sets in and engineers ignore warnings.
- **Alert too slowly:** Budgets blow out from runaway autoscaling or uncontained jobs.
- **Automate blindly:** Fragile LLM scripts risk terminating critical production resources.

CloudCost Sentinel solves this by decoupling the **operational decision** from the **generative explanation**:

### The Signature Decision
> *"Given the spend anomaly, budget pressure, persistence, service criticality and known ownership, should the agent `monitor`, `notify_owner`, or `request_approval` for remediation?"*

```
   ┌────────────────────────────────────────────────────────┐
   │             CloudCost Sentinel Architecture            │
   │                                                        │
   │  [Telemetry Ingestion] ──────► [Mathematical Engine]  │
   │   (AWS Cost Explorer /           (Baseline, Deltas,     │
   │    Synthetic Scenarios)           Persistence Streak)  │
   │                                          │             │
   │                                          ▼             │
   │                              [Strands Decider 2B]     │
   │                               (System 1 Policy Head)   │
   │                                          │             │
   │         ┌────────────────────────────────┼─────────────┐
   │         ▼                                ▼             ▼
   │     [monitor]                    [notify_owner]   [request_approval]
   │  (Passive Watch)                 (Owner Alert)     (Human Sign-off)
   │         │                                │             │
   │         └────────────────────────────────┴─────────────┘
   │                                          │
   │                                          ▼
   │                         [Optional OpenRouter API] │
   │                         (Grounded Investigation Report)│
   │                                          │
   │                                          ▼
   │                           [Operations Command Center]  │
   │                           (React + TypeScript + Vite)  │
   └────────────────────────────────────────────────────────┘
```

---

## 2. Reusable Decision Pattern

**Pattern Name:** Threshold-Aware Anomaly Response
**Pattern Category:** Policy Decision Pattern
**Hackathon Tags:** `#strands-decider-2b` `#policy`
**Pattern Asset Location:** [`patterns/threshold_aware_anomaly_response/`](patterns/threshold_aware_anomaly_response/)

The pattern is packaged with:
- Exact typed `ChoiceQuestion` specification matching Strands Decider schema.
- Native `ThresholdAwareAnomalyIntervention(InterventionHandler)` from the Strands Agents SDK.
- Configurable low-confidence safety fallback (`DECIDER_MIN_CONFIDENCE=0.65`).
- Standalone runnable example (`standalone_example.py`) and automated test suite.

---

## 3. Key Features

- **Decision Provider:** The default is a clearly labeled simulated policy evaluator. An HTTP Decider can be configured separately.
- **Investigation Reports:** Deterministic grounded templates work offline. Optional OpenRouter generation is backend-only and model-selected by environment; it never changes the deterministic decision.
- **Zero-Mutation AWS Safety Sandbox:** Read-only telemetry access. CloudCost Sentinel never executes unverified deletions, instance terminations, or resizing operations on live AWS accounts.
- **Single-Transition Human Approvals:** Supabase production updates are tenant-scoped and use a pending-state compare-and-set; local/demo storage retains SQLite behavior.
- **Calibrated Low-Confidence Fallback:** When telemetry is sparse or ambiguous, Decider's confidence drops below threshold; the system automatically and visibly escalates to `request_approval`.
- **Reproducible Synthetic Scenarios:** Includes 5 deterministic scenarios (Compute Runaway, Database Drift, Batch Surge, Stable Baseline, Sparse Telemetry).
- **Dark Cloud Operations Command Center:** Built with React 19, TypeScript, Vite, and Recharts, providing instant scenario replay, live confidence gauges, and collapsible wire traces.

---

## 4. Quickstart (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 24 and npm (matches the checked-in CI and Docker build toolchain)

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/TechnoKhushal/Cloudcostsentinel.git
cd Cloudcostsentinel

# Create Python virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # Windows PowerShell; on Linux: source .venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 2. Start the FastAPI Backend
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation and OpenAPI Swagger UI: `http://127.0.0.1:8000/docs`

### 3. Start the React Frontend
```bash
cd frontend
npm ci
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 5. Configuration (.env)

The templates are the canonical, complete variable lists: [`.env.example`](.env.example) for backend/local use and [`frontend/.env.example`](frontend/.env.example) for browser-public build values. The backend reads `HOST`, `PORT`, `ENVIRONMENT`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, `AUTH_ENABLED`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DECIDER_PROVIDER`, `STRANDS_DECIDER_URL`, `DECIDER_MODEL_ID`, `DECIDER_MIN_CONFIDENCE`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_HTTP_REFERER`, `OPENROUTER_APP_TITLE`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_COST_EXPLORER_ENABLED`, `AWS_COST_EXPLORER_TIMEZONE`, `AWS_COST_EXPLORER_DAILY_QUERY_LIMIT`, `NOTIFICATION_PROVIDER`, `NOTIFICATION_SNS_TOPIC_ARN`, `DATABASE_PATH`, `DATABASE_URL`, and `ENABLE_TEST_FIXTURE_ENDPOINT`.

The frontend reads only `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`. Vite embeds `VITE_*` values into public browser assets; never place secrets there. Production rate limits use the configured Supabase project and require no additional environment variables.

Detailed documentation:
- [Security Architecture & Threat Model](docs/SECURITY.md)
- [Operations Runbook](docs/RUNBOOK.md)
- [Current Architecture](docs/ARCHITECTURE.md) and [Execution Flow](flow.md)
- [Production Hardening Audit Log](docs/PRODUCTION_HARDENING_LOG.md)
- [Public Simulated Demo Deployment](docs/DEMO_DEPLOYMENT.md)

---

## 6. Optional Live Provider Configuration (Not Verified Here)

### Connecting Real Strands Decider 2B
1. Serve the official model using the `strands-decider` package:
   ```bash
   strands-decider serve --model StrandsAgents/strands-decider-2B-hobson-v19 --port 8080
   ```
2. In `.env`, set:
   ```env
   DECIDER_PROVIDER=http
   STRANDS_DECIDER_URL=http://127.0.0.1:8080/v1/systemone
   ```
3. Restart the API. Configuration does not prove provider connectivity; no live Decider endpoint or checkpoint was verified for this release.

### Connecting OpenRouter (optional)
Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL=openrouter/free` in the backend environment only, or choose a verified model variant ending in `:free`. The backend rejects paid model IDs and does not configure a paid-model fallback. OpenRouter's [free router](https://openrouter.ai/openrouter/free) currently routes only to free variants, though availability and rate limits can change. The app has no default model and never places the key in Vite/browser variables. If unset or unavailable, it uses a clearly labeled deterministic fallback.

### Supabase status
The ordered migrations and deployment steps are documented in [Supabase setup](docs/SUPABASE_SETUP.md). The production adapter is implemented, but no live Supabase project was available to apply or verify the migrations, RLS policies or storage access. Do not enable production traffic until the documented two-account isolation and browser checks pass.

## 7. Hosted Demo / Production Status

For the explicit simulated Render + Vercel demo setup, follow [docs/DEMO_DEPLOYMENT.md](docs/DEMO_DEPLOYMENT.md). Do not use `ENVIRONMENT=development` for hosted Render. Production remains blocked until the migrations are applied and verified, tenant isolation and browser flows pass against an isolated project, AWS role setup and live billing ingestion are exercised, and deployment configuration and production controls are verified. The current production model provisions one personal workspace per user; invitations and multi-member organization administration are not included.

---

## 8. Testing & Verification

Run the automated suites after installing dependencies. This checkout's tests must be rerun in CI or a Python environment containing the repository requirements before their status can be claimed:

```bash
# Run backend test suite
python -m pytest -v tests/test_backend.py

# Run standalone Policy pattern test suite
python -m pytest -v patterns/threshold_aware_anomaly_response/test_pattern.py

# Run standalone runnable pattern script
python patterns/threshold_aware_anomaly_response/standalone_example.py

# Run reproducible latency benchmark
python scripts/benchmark_decider.py --trials 10 --warmup 2
```

The API returns request IDs and security headers, marks API responses `Cache-Control: no-store`, and rejects untrusted Host headers. Production CORS does not enable cookies because the browser uses bearer tokens. The demo's in-process write limiter is demo-only; production authenticated API calls use Supabase-shared per-user limits, with a separate durable quota for billable AWS queries.

---

## 9. Safety & Trust Model

- **Read-Only Telemetry:** AWS Cost Explorer queries are strictly read-only (`ce:GetCostAndUsage`).
- **No Cloud Destruction:** CloudCost Sentinel never executes unverified deletions, instance terminations, or resizing operations on live AWS accounts.
- **Human-in-the-Loop:** Approval transitions are atomic and tenant-scoped in Supabase in production; SQLite remains for local/demo mode.

---

## 10. License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2026 TechnoKhushal.
