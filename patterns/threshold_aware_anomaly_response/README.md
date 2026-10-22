# Reusable Decision Pattern: Threshold-Aware Anomaly Response

**Tags:** `#strands-decider-2b` `#policy`
**Pattern Category:** Policy Decision Pattern
**Domain Demonstrator:** CloudCost Sentinel (Cloud Spending Incident Decision Agent)
**Upstream Engine:** [Strands Decider 2B (`StrandsAgents/strands-decider-2B-hobson-v19`)](https://github.com/strands-labs/strands-decider)

---

## 1. Problem Statement & Motivation

Autonomous monitoring systems in production face a fundamental dilemma when an operational anomaly is detected:
- **Over-alerting** causes operational fatigue and pager numbness.
- **Silent monitoring** risks budget blowout, runaway autoscaling, or uncontained outages.
- **Unchecked automated remediation** risks terminating live production resources without human approval.

Traditional rule engines rely on rigid boolean thresholds that fail to account for multi-dimensional context (such as verified ownership, environmental criticality, persistence duration, and budget velocity).

The **Threshold-Aware Anomaly Response** pattern uses **Strands Decider 2B** as a fast, calibrated "System 1" decision engine to choose the operational response:
1. `monitor`: Passive observation. Suitable for transient fluctuations, non-critical environments, or workloads well within budget headroom.
2. `notify_owner`: Direct notification to the verified resource owner. Suitable for moderate drift where an assigned owner can investigate without disruptive intervention.
3. `request_approval`: Human escalation review item. Mandatory for severe spend spikes, unassigned ownership, runaway budget burn, or high-uncertainty telemetry.

---

## 2. Where to Use This Pattern

- **Cloud Cost & FinOps Automation:** Autonomous triage of AWS/GCP/Azure bill drift.
- **SRE & Infrastructure Health:** Auto-remediation gates for Kubernetes pods, autoscaling groups, or disk utilization.
- **API Rate-Limiting & Security:** Threshold-aware IP blocking vs throttling vs human SOC escalation.
- **Data Pipeline Anomaly Triage:** Deciding whether to pause a streaming job or notify the data engineering owner.

---

## 3. The Exact Decider 2B Typed Specification

### Question Specification (`ChoiceQuestion`)

```python
from strands_decider.schema import ChoiceQuestion

question = ChoiceQuestion(
    type="choice",
    instructions=(
        "Given the spend anomaly, budget pressure, persistence, service criticality "
        "and known ownership, should the agent monitor, notify_owner, or request_approval for remediation?"
    ),
    criteria={
        "monitor": (
            "Observe and re-evaluate without alerting. Appropriate for small fluctuations, "
            "low budget impact, or non-critical environments."
        ),
        "notify_owner": (
            "Notify the verified resource owner directly. Appropriate for known service owners "
            "with moderate budget pressure or early-stage anomalies."
        ),
        "request_approval": (
            "Escalate to human cloud platform engineer for remediation sign-off. Appropriate for high spend spikes, "
            "runaway budget burn, unassigned owners, or critical production environments."
        ),
    },
)
```

### Compact Normalized State Format

To maximize latency benefits and model focus, pass a compact normalized text string rather than an unformatted raw payload:

```text
Service: Amazon EC2 | Environment: production (Criticality: CRITICAL)
Spend Delta: +$897.08/day (+202.5%) above baseline $442.92
Current Daily Spend: $1,340.00 | Persistence: 3 consecutive days
Budget Utilization: 237.8% consumed of $12,000.00 monthly budget | Forecast: $28,538.00
Owner: unassigned / unknown | Measurement Uncertainty: LOW
```

---

## 4. Strands Agents SDK Intervention Handler Wiring

In an agentic workflow, this policy acts as a **Strands InterventionHandler** intercepting actions before tool execution:

```python
from strands.interventions.handler import InterventionHandler
from strands.interventions.actions import Proceed, Guide, Confirm
from strands.hooks.events import BeforeToolCallEvent

class ThresholdAwareAnomalyIntervention(InterventionHandler):
    name = "threshold-aware-anomaly-response"

    def __init__(self, policy_evaluator, current_anomaly):
        super().__init__()
        self.policy_evaluator = policy_evaluator
        self.current_anomaly = current_anomaly

    async def before_tool_call(self, event: BeforeToolCallEvent):
        # Evaluate Decider 2B on the real decision boundary
        result = await self.policy_evaluator.evaluate(self.current_anomaly)

        if result.action == "monitor":
            return Proceed(reason=f"Decider chose monitor ({result.confidence:.2f}). Passive observation.")
        elif result.action == "notify_owner":
            return Guide(feedback=f"Alert owner {self.current_anomaly.owner} before mutative changes.")
        else: # "request_approval"
            return Confirm(prompt="Spend spike requires human review and sign-off.")
```

---

## 5. Low-Confidence & Safety Fallback Logic

Strands Decider 2B provides a mathematically calibrated confidence score:
$$\text{confidence} = \frac{N \times p_{\max} - 1}{N - 1}$$

If model confidence drops below the configured safety threshold (`min_confidence=0.65`), or if an inference timeout/error occurs, the pattern **never silently proceeds**. It automatically escalates to `request_approval`:

```python
if confidence < self.min_confidence:
    is_fallback = True
    action = "request_approval"
    fallback_reason = (
        f"Confidence {confidence:.3f} below safety threshold {self.min_confidence:.3f}. "
        f"Conservatively escalating to human review."
    )
```

---

## 6. How Another Builder Can Reuse This Pattern

1. Copy the pattern folder `patterns/threshold_aware_anomaly_response/` into your project.
2. Adapt the `AnomalyState` class to your domain metrics (e.g., latency, error rate, memory).
3. Connect your Decider 2B host endpoint (`http://localhost:8000/v1/systemone` or hosted service).
4. Run the standalone test suite:
   ```bash
   python -m pytest patterns/threshold_aware_anomaly_response/test_pattern.py -v
   ```
5. Run the standalone runnable demo:
   ```bash
   python patterns/threshold_aware_anomaly_response/standalone_example.py
   ```

---

## 7. Assumptions and Limitations

- **Decider Model Scope:** Strands Decider 2B is a System 1 pointer-choice model; it selects strictly from predefined options and does not generate conversational prose (Amazon Bedrock provides the generative narrative layer).
- **Experimental Model:** Decider 2B is an experimental model under active development by Strands Labs; use conservative confidence thresholds (`>= 0.65`) for automated actions.
- **Human-in-the-Loop:** For safety, CloudCost Sentinel does not mutate cloud resources directly. All `request_approval` outcomes require human sign-off.
