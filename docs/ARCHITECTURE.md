# CloudCost Sentinel — Architecture & System Design

**Tags:** `#strands-decider-2b` `#policy`

**Current runtime note:** The default environment uses simulated providers. The Decider and Bedrock boxes below describe optional integration points; `configured_unverified` is not evidence of a live connection. Hosted public demo uses `ENVIRONMENT=demo`, synthetic scenarios, mock providers, and SQLite on a persistent disk.

---

## 1. High-Level System Overview

CloudCost Sentinel decouples the **System 1 operational choice** (fast, low-latency pointer decision) from the **generative investigation narrative** (grounded reasoning report).

```mermaid
flowchart TD
    subgraph Data Layer
        CE["AWS Cost Explorer (Read-Only)"] -.->|Optional Live Telemetry| Ingestion
        SimData["Synthetic Scenario Engine"] -->|Deterministic Data| Ingestion["Telemetry Ingestion & Normalization"]
    end

    subgraph Analysis & Mathematical Engine
        Ingestion --> Math["Statistical Windowing & Metric Calculations"]
        Math -->|Normalized State| Boundary{"Threshold-Aware Anomaly Policy"}
    end

    subgraph Decision Boundary
        Boundary -->|Compact State & ChoiceQuestion| Decider["Strands Decider 2B<br/>(Pointer Decision Head)"]
        Decider -->|Choice + Calibrated Confidence| ConfCheck{"Confidence >= 0.65?"}
        ConfCheck -->|Yes| ActionRouting["Action Router"]
        ConfCheck -->|No / Error| SafetyFallback["Safety Override<br/>(Fallback: request_approval)"]
        SafetyFallback --> ActionRouting
    end

    subgraph Execution & Intervention
        ActionRouting -->|monitor| ObsLog["Passive Observation Event"]
        ActionRouting -->|notify_owner| AlertQueue["Owner Notification Dispatch"]
        ActionRouting -->|request_approval| ApprQueue["Human Approval Queue"]
    end

    subgraph Generative Narrative Layer
        Math --> BedrockNarrator["Strands Agents SDK + Amazon Bedrock"]
        ActionRouting --> BedrockNarrator
        BedrockNarrator --> GroundedReport["Grounded Investigation Report<br/>(Facts, Audit, Safe Steps)"]
    end

    subgraph Storage & Presentation
        ObsLog --> SQLite[("SQLite Database Repository")]
        AlertQueue --> SQLite
        ApprQueue --> SQLite
        GroundedReport --> SQLite
        SQLite --> UI["Cloud Operations Command Center<br/>(React + Vite + Recharts)"]
    end
```

---

## 2. Component Responsibilities

| Component | Responsibility | Boundary & Constraints |
| :--- | :--- | :--- |
| **Telemetry Ingestion & Formulas** | Computes baseline, delta amount, delta percentage, persistence streak, budget velocity, and data uncertainty. | Deterministic mathematics; no magic thresholds. Excludes recent spikes from baseline to avoid metric pollution. |
| **Strands Decider 2B** | Evaluates normalized state against exact `ChoiceQuestion` (`monitor`, `notify_owner`, `request_approval`). Returns argmax choice and calibrated confidence. | Zero open-ended text generation; strictly evaluates typed options in a single forward pass. |
| **Confidence Guard & Fallback** | Monitors calibrated model confidence against `DECIDER_MIN_CONFIDENCE` (default 0.65). If below threshold or if inference fails, forces `request_approval`. | High-assurance safety mechanism preventing autonomous under-reaction to ambiguous telemetry. |
| **Strands Intervention Handler** | Implements `ThresholdAwareAnomalyIntervention(InterventionHandler)` from the Strands Agents SDK to gate agent tools prior to execution. | Maps `monitor` -> `Proceed`, `notify_owner` -> `Guide`, and `request_approval` -> `Confirm`. |
| **Amazon Bedrock Narrator** | Synthesizes observed metric facts into an executive summary, evidence timeline, Decider action audit, and safe recommendations. | Strictly grounded on observed facts; never invents AWS resource IDs, prices, or untracked causes. Never overrides Decider's choice. |
| **Human Review Queue** | Stores pending remediation recommendations for manual engineer sign-off. | Non-mutative sandbox; human approval updates internal audit state without triggering live resource deletions. |
| **Command Center UI** | Dark cloud operations dashboard displaying real-time spend curves, Decider choices, wire-level traces, Bedrock reports, and approval buttons. | Fast React 19 + TypeScript + Vite frontend with accessible contrast and instant scenario replay. |

---

## 3. Trust Boundaries & AWS Safety Model

1. **Read-Only Telemetry:**
   - AWS Cost Explorer client connects with strictly read-only permissions (`ce:GetCostAndUsage`, `sts:GetCallerIdentity`).
   - Default is `AWS_COST_EXPLORER_ENABLED=false` so the app runs out-of-the-box deterministically.

2. **No Mutative IAM Permissions:**
   - The agent has zero IAM permissions for `ec2:TerminateInstances`, `ec2:ModifyInstanceAttribute`, `autoscaling:UpdateAutoScalingGroup`, or `rds:ModifyDBInstance`.
   - The product's signature is **decision guidance and human approval creation**, not unverified destruction.

3. **Zero Secret Leakage:**
   - No credentials or API keys are ever committed, logged, or returned in HTTP API responses.
