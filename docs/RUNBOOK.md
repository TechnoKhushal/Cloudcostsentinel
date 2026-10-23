# Operations Runbook — CloudCost Sentinel

This runbook provides step-by-step operational procedures for running, monitoring, migrating, and troubleshooting CloudCost Sentinel.

For a hosted public synthetic demo, use [DEMO_DEPLOYMENT.md](DEMO_DEPLOYMENT.md). The browser UI does not yet implement OIDC login; do not treat it as a usable authenticated production dashboard.

---

## 1. Quick Start & Execution Modes

### Mode A: Local Development Demo (Zero AWS Credentials)
The default out-of-the-box configuration runs completely locally with calibrated synthetic scenarios and explicit `SIMULATED` badges.

```bash
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # Linux / macOS

# 2. Run backend (port 8000)
python -m uvicorn backend.main:app --reload --port 8000

# 3. In another terminal, run frontend (port 5173)
cd frontend
npm run dev
```
Open [http://localhost:5173](http://localhost:5173). The dashboard runs with:
- **Decider 2B**: Deterministic mock policy evaluator (`demo-policy-evaluator-v1`)
- **Bedrock**: Deterministic grounded template narrator (`grounded-template-narrator-v1`)
- **Cost Data**: 5 deterministic scenarios (`compute_spike`, `database_drift`, etc.)

---

### Mode B: Real Strands Decider 2B (Local Model Serving)
To connect CloudCost Sentinel to the genuine Strands Decider 2B model:

1. In a dedicated Python environment with PyTorch and CUDA/MPS:
   ```bash
   pip install strands-decider
   strands-decider serve --model StrandsAgents/strands-decider-2B-hobson-v19 --port 8080
   ```
2. In `.env`:
   ```ini
   DECIDER_PROVIDER=http
   STRANDS_DECIDER_URL=http://127.0.0.1:8080/v1/systemone
   ```
3. Restart CloudCost Sentinel. The API calls the real Decider 2B server over HTTP, validates probabilities and confidence, and reports `provider: strands-decider-2b-http`.

---

### Mode C: Live Amazon Bedrock (Cloud Narrative Reports)
1. Ensure AWS credentials are configured via standard AWS CLI:
   ```bash
   aws configure
   ```
2. Enable model access in AWS Bedrock console for `us.anthropic.claude-3-7-sonnet-20250219-v1:0` in `us-east-1`.
3. In `.env`:
   ```ini
   BEDROCK_PROVIDER=bedrock
   AWS_REGION=us-east-1
   ```
4. Restart CloudCost Sentinel. A successful real invocation depends on credentials and model access; this setup is not live-verified here.

---

## 2. Health & Liveness Checks

CloudCost Sentinel exposes two distinct probes:

### 1. Cheap Liveness Probe: `GET /api/health/live`
- Returns: `{"status": "ok"}` with HTTP 200.
- Purpose: Kubernetes liveness / AWS ECS health checks. Performs zero external I/O.

### 2. Service Summary: `GET /api/health`
- Reports configured/simulated provider states without asserting external connectivity.

### 3. Readiness Probe: `GET /api/health/ready`
- Checks the SQLite repository and required provider state. In `ENVIRONMENT=demo`, simulated providers are expected. In production, providers currently remain unverified until bounded live checks are implemented.
  ```json
  {
    "status": "ready",
    "environment": "demo",
    "checks": {
      "database": "connected",
      "decider": "simulated",
      "bedrock": "simulated"
    }
  }
  ```

---

## 3. Database Management & Schema Migrations

### Local SQLite Persistence
- Default path: `backend/data/sentinel.db`
- Connection mode: WAL mode (`PRAGMA journal_mode=WAL`) with 5000ms busy timeout.
- Schema upgrades: `DatabaseRepository._init_tables()` automatically inspects existing columns and applies backwards-compatible migrations (e.g. adding `is_simulated INTEGER DEFAULT 1` to `approvals` without data loss).

### Backup & Restore
```bash
# Backup SQLite database
sqlite3 backend/data/sentinel.db ".backup 'backend/data/sentinel_backup_$(date +%Y%m%d).db'"
```

---

## 4. Benchmark & Performance Reproducibility

Run the calibrated Decider benchmark script:
```bash
python scripts/benchmark_decider.py --trials 10 --warmup 2
```
Output files are written to `scripts/benchmark_results/` (git-ignored) with statistical summaries (min, max, median, p95).

---

## 5. Troubleshooting & Common Provider Errors

| Issue | Cause | Resolution |
|-------|-------|------------|
| `Startup failed: STRANDS_DECIDER_URL points to app port 8000` | Misconfigured self-referential HTTP URL | Change `STRANDS_DECIDER_URL` to point to port 8080 (the external `strands-decider serve` process). |
| `HTTP 409 Conflict: Approval was already reviewed` | Replay attempt on approved/rejected item | Normal idempotency behavior. Approvals can only transition from pending once. |
| `HTTP 422: Invalid scenario_id` | Unknown scenario passed to `/api/analyze` | Choose one of the valid scenarios: `compute_spike`, `database_drift`, `batch_surge`, `stable_baseline`, `low_confidence_drift`. |
| `AccessDeniedException on Cost Explorer` | Missing `ce:GetCostAndUsage` IAM permission | Attach read-only Cost Explorer policy to AWS credentials or keep `AWS_COST_EXPLORER_ENABLED=false`. |
