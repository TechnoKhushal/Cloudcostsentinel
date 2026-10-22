# CloudCost Sentinel — Autonomous Cloud Spend Decision Agent

[![CI](https://github.com/TechnoKhushal/Cloudcostsentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/TechnoKhushal/Cloudcostsentinel/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tags](https://img.shields.io/badge/Tags-%23strands--decider--2b%20%7C%20%23policy-purple)](#hackathon-classification)

> **CloudCost Sentinel** reviews cloud usage metrics, detects and explains cost anomalies, and uses **Strands Decider 2B** to choose the operational response. **Amazon Bedrock** (via the **Strands Agents SDK**) performs the generative work: explaining why the anomaly matters and drafting a grounded cost investigation report.

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
   │                        [Strands Agents SDK + Bedrock] │
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

- **Strands Decider 2B in the Main Path:** Evaluates multi-dimensional telemetry (`service`, `criticality`, `spend_delta`, `budget_burn`, `persistence`, `ownership`) in a single forward pass without token-generation latency.
- **Amazon Bedrock Grounded Narrative:** Generates executive summaries, evidence timelines, Decider choice audits, and safe investigation steps strictly grounded in observed telemetry.
- **Zero-Mutation AWS Safety Sandbox:** Read-only telemetry access. CloudCost Sentinel never executes unverified deletions, instance terminations, or resizing operations on live AWS accounts.
- **Calibrated Low-Confidence Fallback:** When telemetry is sparse or ambiguous, Decider's confidence drops below threshold; the system automatically and visibly escalates to `request_approval`.
- **Reproducible Synthetic Scenarios:** Includes 5 deterministic scenarios (Compute Runaway, Database Drift, Batch Surge, Stable Baseline, Sparse Telemetry).
- **Dark Cloud Operations Command Center:** Built with React 19, TypeScript, Vite, and Recharts, providing instant scenario replay, live confidence gauges, and collapsible wire traces.

---

## 4. Quickstart (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 20+ and npm

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/TechnoKhushal/Cloudcostsentinel.git
cd Cloudcostsentinel

# Create Python virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

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
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 5. Configuration (.env)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DECIDER_PROVIDER` | `mock` | `mock` (simulated adapter), `http` (local/remote `strands-decider serve`), or `inprocess` |
| `STRANDS_DECIDER_URL` | `http://127.0.0.1:8000/v1/systemone` | HTTP endpoint serving Strands Decider wire protocol |
| `DECIDER_MODEL_ID` | `StrandsAgents/strands-decider-2B-hobson-v19` | Strands Decider model identifier |
| `DECIDER_MIN_CONFIDENCE` | `0.65` | Confidence threshold below which the agent conservatively falls back to `request_approval` |
| `BEDROCK_PROVIDER` | `mock` | `mock` (deterministic grounded narrative adapter) or `bedrock` (live Amazon Bedrock) |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock and Cost Explorer |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-3-7-sonnet-20250219-v1:0` | Amazon Bedrock foundation model ID |
| `AWS_COST_EXPLORER_ENABLED`| `false` | Read-only live AWS Cost Explorer queries (disabled by default) |
| `DATABASE_PATH` | `backend/data/sentinel.db` | SQLite database path for decision traces and approvals |

---

## 6. Live Provider Integration

### Connecting Real Strands Decider 2B
1. Serve the official model using the `strands-decider` package:
   ```bash
   strands-decider serve StrandsAgents/strands-decider-2B-hobson-v19 --port 8080
   ```
2. In `.env`, set:
   ```env
   DECIDER_PROVIDER=http
   STRANDS_DECIDER_URL=http://127.0.0.1:8080/v1/systemone
   ```

### Connecting Amazon Bedrock
1. Configure your AWS credentials via `aws configure` or environment variables:
   ```bash
   export AWS_REGION=us-east-1
   export AWS_ACCESS_KEY_ID=...
   export AWS_SECRET_ACCESS_KEY=...
   ```
2. Enable model access for `Anthropic Claude 3.7 Sonnet` in your AWS Bedrock Console.
3. In `.env`, set:
   ```env
   BEDROCK_PROVIDER=bedrock
   ```

---

## 7. Testing & Verification

Run the full automated test suite (backend formulas, Decider routing, Bedrock grounding, safety fallbacks, and the Policy pattern):

```bash
# Run backend test suite (15 passed)
python -m pytest -v tests/test_backend.py

# Run standalone Policy pattern test suite (5 passed)
python -m pytest -v patterns/threshold_aware_anomaly_response/test_pattern.py

# Run standalone runnable pattern script
python patterns/threshold_aware_anomaly_response/standalone_example.py

# Run reproducible latency benchmark
python scripts/benchmark_decider.py --trials 10 --warmup 2
```

---

## 8. Safety & Trust Model

- **Read-Only Telemetry:** AWS Cost Explorer queries are strictly read-only (`ce:GetCostAndUsage`).
- **No Cloud Destruction:** CloudCost Sentinel never executes unverified deletions, instance terminations, or resizing operations on live AWS accounts.
- **Human-in-the-Loop:** Approvals recorded in the dashboard update internal review states in the SQLite audit log and never trigger blind mutations.

---

## 9. License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2026 TechnoKhushal.
